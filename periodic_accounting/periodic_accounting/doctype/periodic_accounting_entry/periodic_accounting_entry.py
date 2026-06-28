import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate
from erpnext.accounts.utils import get_stock_and_account_balance


class PeriodicAccountingEntry(Document):

	def validate(self):
		self.validate_company()
		self.validate_accounts()
		self.validate_dates()

	def validate_dates(self):
		if self.from_date and self.posting_date:
			if getdate(self.from_date) >= getdate(self.posting_date):
				frappe.throw(_("From Date (Period Start) must be before Posting Date (Period End)."))

	def validate_company(self):
		if frappe.db.get_value("Company", self.company, "enable_perpetual_inventory"):
			frappe.throw(
				_(
					"Periodic Accounting Entry is only for companies with "
					"Perpetual Inventory DISABLED. Company {0} has perpetual "
					"inventory enabled. Use standard ERPNext for COGS tracking."
				).format(frappe.bold(self.company))
			)

	def validate_accounts(self):
		if not self.closing_stock_account:
			frappe.throw(_("Please select a Closing Stock Account (Income Statement)."))
		if not self.for_all_stock_accounts and not self.stock_account:
			frappe.throw(_("Please select a Stock Account or tick 'For All Stock Accounts'."))

	def on_submit(self):
		self.validate_repost_item_valuation()
		self.create_opening_stock_journal_entry()
		self.create_journal_entry()

	def on_cancel(self):
		self.cancel_journal_entry()
		self.cancel_opening_stock_journal_entry()

	@frappe.whitelist()
	def get_balance(self):
		"""
		Reads tabBin (live stock value) vs GL Account balance via ERPNext's
		get_stock_and_account_balance — which automatically maps each stock account
		to its linked warehouses when multiple stock accounts exist.
		Auto-populates the accounts child table.
		"""
		self.validate_company()

		stock_accounts = self.get_stock_accounts()
		self.set("accounts", [])
		log_lines = []
		total_difference = 0

		for account in stock_accounts:
			account_bal, stock_bal, _wh = get_stock_and_account_balance(
				account, self.posting_date, self.company
			)

			# When from_date is set, the Opening Stock JE will zero out the GL balance
			# for this account on from_date.  The Closing JE therefore needs to cover
			# the FULL current stock value — not just the incremental change — so we
			# subtract the prior GL balance from account_bal before computing difference.
			if self.from_date:
				result = frappe.db.sql(
					"""SELECT COALESCE(SUM(debit - credit), 0) AS bal
					   FROM `tabGL Entry`
					   WHERE account = %s AND posting_date < %s AND is_cancelled = 0""",
					(account, self.from_date), as_dict=True,
				)
				opening_gl = flt(result[0].bal) if result else 0.0
				account_bal = flt(account_bal - opening_gl, 3)

			# positive → stock > GL: stock in (Dr Inventory / Cr COGS)
			# negative → stock < GL: stock out (Dr COGS / Cr Inventory)
			difference = flt(stock_bal - account_bal, 3)

			log_lines.append(
				f"{account}: GL={account_bal:.3f} | "
				f"Stock Reg (tabBin)={stock_bal:.3f} | Diff={difference:.3f}"
			)

			if difference == 0:
				frappe.msgprint(
					_("No difference found for {0} — skipping").format(frappe.bold(account)),
					alert=True,
				)
				continue

			total_difference += difference
			account_name = frappe.db.get_value("Account", account, "account_name")

			self.append(
				"accounts",
				{
					"account": account,
					"account_name": account_name,
					"debit": difference if difference > 0 else 0,
					"credit": abs(difference) if difference < 0 else 0,
					"remarks": (
						f"Inventory (Balance Sheet) periodic entry as at {self.posting_date} | "
						f"GL: {account_bal:.3f} | Stock Reg: {stock_bal:.3f}"
					),
				},
			)

			closing_stock_account_name = frappe.db.get_value(
				"Account", self.closing_stock_account, "account_name"
			)

			self.append(
				"accounts",
				{
					"account": self.closing_stock_account,
					"account_name": closing_stock_account_name,
					"debit": abs(difference) if difference < 0 else 0,
					"credit": difference if difference > 0 else 0,
					"remarks": f"Closing Stock (Income Statement) offset for {account_name}",
				},
			)

		self.remarks = (
			f"Periodic Accounting Entry — {self.posting_date}\n"
			+ "\n".join(log_lines)
			+ f"\n\nTotal Net Difference: {total_difference:.3f}"
		)

		if total_difference == 0:
			frappe.msgprint(
				_("Stock register matches GL perfectly. No entry needed."),
				indicator="green",
			)
		else:
			frappe.msgprint(
				_(
					"Balance calculated. Net difference: {0}. "
					"Review the accounts table and Submit to post the Journal Entry."
				).format(frappe.bold(f"{total_difference:.3f}")),
				indicator="blue",
			)

	def validate_repost_item_valuation(self):
		"""Block submission if any Repost Item Valuation job on or before posting_date is not done."""
		pending = frappe.db.get_all(
			"Repost Item Valuation",
			filters={
				"company": self.company,
				"posting_date": ["<=", self.posting_date],
				"status": ["in", ["Queued", "In Progress", "Failed"]],
				"docstatus": 1,
			},
			fields=["name", "posting_date", "status"],
			order_by="posting_date asc",
		)
		if not pending:
			return

		links = ", ".join(
			frappe.utils.get_link_to_form("Repost Item Valuation", d.name)
			+ f" ({d.status} — {d.posting_date})"
			for d in pending
		)
		frappe.throw(
			_(
				"Cannot submit: {0} Repost Item Valuation job(s) on or before {1} "
				"have not completed — stock valuations may still be recalculating.<br><br>{2}<br><br>"
				"Please wait for all repost jobs to reach <strong>Completed</strong> status "
				"before posting a Periodic Accounting Entry."
			).format(len(pending), frappe.bold(str(self.posting_date)), links),
			title=_("Pending Repost Item Valuation"),
		)

	def create_opening_stock_journal_entry(self):
		"""
		Reverses the prior GL inventory balance into the Closing Stock (Income Statement)
		account on `from_date`, so the period P&L shows:
		  Dr  Closing Stock A/c (IS)  ←  opening stock (cost side)
		  Cr  Inventory A/c  (BS)     ←  removes it from balance sheet
		The paired closing stock JE at period end then restores it:
		  Dr  Inventory A/c  (BS)
		  Cr  Closing Stock A/c (IS)
		Net IS impact = closing stock − opening stock = correct COGS reduction.
		"""
		if not self.from_date:
			return

		stock_accounts = self.get_stock_accounts()
		je_rows = []

		for account in stock_accounts:
			result = frappe.db.sql(
				"""SELECT COALESCE(SUM(debit - credit), 0) AS bal
				   FROM `tabGL Entry`
				   WHERE account = %s AND posting_date < %s AND is_cancelled = 0""",
				(account, self.from_date),
				as_dict=True,
			)
			gl_balance = flt(result[0].bal) if result else 0.0

			if gl_balance == 0:
				continue

			account_name = frappe.db.get_value("Account", account, "account_name")
			base_remark = f"as at {self.from_date} | Prior GL balance: {gl_balance:.3f}"
			dim_vals = self._get_accounting_dimension_values(account)
			row_extra = {**dim_vals}
			if self.cost_center:
				row_extra["cost_center"] = self.cost_center

			if gl_balance > 0:
				je_rows.append({
					**row_extra,
					"account": self.closing_stock_account,
					"debit_in_account_currency": gl_balance,
					"credit_in_account_currency": 0,
					"user_remark": f"Opening Stock (Income Statement) for {account_name} {base_remark}",
				})
				je_rows.append({
					**row_extra,
					"account": account,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": gl_balance,
					"user_remark": f"Inventory (Balance Sheet) opening reversal for {account_name} {base_remark}",
				})
			else:
				abs_bal = abs(gl_balance)
				je_rows.append({
					**row_extra,
					"account": self.closing_stock_account,
					"debit_in_account_currency": 0,
					"credit_in_account_currency": abs_bal,
					"user_remark": f"Opening Stock reversal (negative) for {account_name} {base_remark}",
				})
				je_rows.append({
					**row_extra,
					"account": account,
					"debit_in_account_currency": abs_bal,
					"credit_in_account_currency": 0,
					"user_remark": f"Inventory (Balance Sheet) negative opening for {account_name} {base_remark}",
				})

		if not je_rows:
			frappe.msgprint(
				_("No prior GL inventory balance found before {0} — Opening Stock Journal Entry skipped.").format(
					frappe.bold(str(self.from_date))
				),
				alert=True,
			)
			return

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.from_date
		je.company = self.company
		je.user_remark = (
			f"[OPENING STOCK ENTRY] {self.name} | Opening Stock as at {self.from_date}"
		)
		for r in je_rows:
			je.append("accounts", r)

		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("opening_stock_journal_entry", je.name, commit=True)

		frappe.msgprint(
			_("Opening Stock Journal Entry {0} created and submitted.").format(
				frappe.utils.get_link_to_form("Journal Entry", je.name)
			),
			indicator="green",
		)

	def cancel_opening_stock_journal_entry(self):
		if self.opening_stock_journal_entry:
			je_doc = frappe.get_doc("Journal Entry", self.opening_stock_journal_entry)
			if je_doc.docstatus == 1:
				je_doc.cancel()
			self.db_set("opening_stock_journal_entry", None, commit=True)

	def _get_accounting_dimension_values(self, account):
		"""Pull accounting dimension field values from the most-recent GL entry for an account.
		Allows auto-created JEs to satisfy mandatory dimension requirements without UI changes."""
		try:
			from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
				get_accounting_dimensions,
			)
			dimensions = get_accounting_dimensions()
		except Exception:
			return {}
		if not dimensions:
			return {}
		fields = ", ".join(f"`{d}`" for d in dimensions)
		result = frappe.db.sql(
			f"""SELECT {fields}
			    FROM `tabGL Entry`
			    WHERE account = %s AND company = %s AND is_cancelled = 0
			    ORDER BY posting_date DESC, creation DESC LIMIT 1""",
			(account, self.company), as_dict=True,
		)
		if result:
			return {d: result[0].get(d) for d in dimensions if result[0].get(d)}
		return {}

	def get_stock_accounts(self):
		if self.for_all_stock_accounts:
			# Include every non-group Asset account typed as Stock.
			# Also pick up accounts that are linked to at least one warehouse
			# but may not carry the "Stock" account_type label explicitly.
			stock_typed = frappe.get_all(
				"Account",
				filters={
					"company": self.company,
					"root_type": "Asset",
					"account_type": "Stock",
					"is_group": 0,
				},
				pluck="name",
			)
			# Accounts linked to a warehouse but missing the account_type tag
			wh_linked = frappe.db.sql_list("""
				SELECT DISTINCT w.account
				FROM `tabWarehouse` w
				WHERE w.company = %s AND w.account IS NOT NULL AND w.account != ''
			""", self.company)
			return list({*stock_typed, *wh_linked})
		return [self.stock_account]

	def create_journal_entry(self):
		if not self.accounts:
			frappe.throw(_("No accounts to post. Click 'Get Balance' first."))

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.posting_date
		je.company = self.company
		je.user_remark = (
			f"[PERIODIC ACCOUNTING ENTRY] {self.name} | "
			f"Auto-generated entry as at {self.posting_date}"
		)

		for row in self.accounts:
			dim_vals = self._get_accounting_dimension_values(row.account)
			je_row = {
				**dim_vals,
				"account": row.account,
				"debit_in_account_currency": row.debit,
				"credit_in_account_currency": row.credit,
				"user_remark": row.remarks,
			}
			if self.cost_center:
				je_row["cost_center"] = self.cost_center
			je.append("accounts", je_row)

		je.insert(ignore_permissions=True)
		je.submit()
		self.db_set("journal_entry", je.name, commit=True)

		frappe.msgprint(
			_("Journal Entry {0} created and submitted successfully.").format(
				frappe.utils.get_link_to_form("Journal Entry", je.name)
			),
			indicator="green",
		)

	def cancel_journal_entry(self):
		if self.journal_entry:
			je_doc = frappe.get_doc("Journal Entry", self.journal_entry)
			if je_doc.docstatus == 1:
				je_doc.cancel()
			self.db_set("journal_entry", None, commit=True)
