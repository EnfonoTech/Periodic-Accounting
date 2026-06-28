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
		Generates the traditional periodic inventory closing entry:
		  Cr  Purchases accounts  — close out purchases expense for the period
		  Dr  Inventory account   — record closing stock on the Balance Sheet
		  Dr  Periodic Entry Diff — actual Net COGS (balancing figure)

		Formula: COGS = Purchases (GL) - Net Inventory Change
		         Net Inventory Change = Closing Stock (Bin) - Prior Inventory GL (adjusted for opening JE)
		"""
		self.validate_company()

		stock_accounts = self.get_stock_accounts()
		self.set("accounts", [])
		log_lines = []

		period_start = self.from_date if self.from_date else "1900-01-01"

		# ── 1. Purchases from GL for the period ──────────────────────────────
		# Captures all inbound stock costs on Expense accounts:
		#   Purchase Invoice  — local (company currency) and import (foreign currency, GL in base)
		#                       Negative net = purchase returns (Cr > Dr), handled by debit - credit
		#   Landed Cost Voucher — freight, customs duty, other landed costs allocated to items
		#                         These raise the Bin/SLE valuation but post to separate expense accounts
		purchase_rows = frappe.db.sql(
			"""SELECT gle.account,
			          COALESCE(SUM(gle.debit - gle.credit), 0) AS amount
			   FROM `tabGL Entry` gle
			   INNER JOIN `tabAccount` acc ON acc.name = gle.account
			   WHERE gle.company = %s
			     AND gle.posting_date BETWEEN %s AND %s
			     AND gle.voucher_type IN (
			         'Purchase Invoice',
			         'Purchase Receipt',
			         'Landed Cost Voucher'
			     )
			     AND acc.root_type = 'Expense'
			     AND gle.is_cancelled = 0
			   GROUP BY gle.account
			   HAVING COALESCE(SUM(gle.debit - gle.credit), 0) != 0""",
			(self.company, period_start, self.posting_date),
			as_dict=True,
		)
		total_purchases = sum(flt(r.amount) for r in purchase_rows)
		log_lines.append(f"Purchases (GL, {period_start} → {self.posting_date}): {total_purchases:.3f}")

		# ── 2. Net inventory change per stock account ─────────────────────────
		# account_bal is adjusted for the opening-stock JE that will zero out the
		# prior-period GL balance when from_date is set (same logic as before).
		inventory_rows = []
		total_net_change = 0.0

		for account in stock_accounts:
			account_bal_raw, stock_bal, _wh = get_stock_and_account_balance(
				account, self.posting_date, self.company
			)
			account_bal = flt(account_bal_raw)

			if self.from_date:
				result = frappe.db.sql(
					"""SELECT COALESCE(SUM(debit - credit), 0) AS bal
					   FROM `tabGL Entry`
					   WHERE account = %s AND posting_date < %s AND is_cancelled = 0""",
					(account, self.from_date), as_dict=True,
				)
				opening_gl = flt(result[0].bal) if result else 0.0
				account_bal = flt(account_bal_raw - opening_gl, 3)

			net_change = flt(stock_bal - account_bal, 3)
			total_net_change += net_change

			log_lines.append(
				f"{account}: GL(adj)={account_bal:.3f} | Bin={stock_bal:.3f} | ΔInventory={net_change:.3f}"
			)

			if net_change == 0:
				continue

			account_name = frappe.db.get_value("Account", account, "account_name")
			inventory_rows.append({
				"account": account,
				"account_name": account_name,
				"debit": net_change if net_change > 0 else 0,
				"credit": abs(net_change) if net_change < 0 else 0,
				"remarks": (
					f"Closing Stock (Balance Sheet) as at {self.posting_date} | "
					f"Bin: {stock_bal:.3f} | GL (period-adj): {account_bal:.3f}"
				),
			})

		# ── 3. COGS = Purchases − Net Inventory Change ────────────────────────
		cogs = flt(total_purchases - total_net_change, 3)
		log_lines.append(f"Net Inventory Change: {total_net_change:.3f}")
		log_lines.append(f"Net COGS            : {cogs:.3f}")

		# ── 4. Append rows in accountant's order: Purchases → Inventory → COGS ─
		for r in purchase_rows:
			amount = flt(r.amount, 3)
			account_name = frappe.db.get_value("Account", r.account, "account_name")
			self.append("accounts", {
				"account": r.account,
				"account_name": account_name,
				"debit": 0 if amount > 0 else abs(amount),
				"credit": amount if amount > 0 else 0,
				"remarks": f"Close Purchases to Trading Account | {period_start} → {self.posting_date}",
			})

		for row in inventory_rows:
			self.append("accounts", row)

		if cogs != 0:
			cogs_name = frappe.db.get_value("Account", self.closing_stock_account, "account_name")
			self.append("accounts", {
				"account": self.closing_stock_account,
				"account_name": cogs_name,
				"debit": cogs if cogs > 0 else 0,
				"credit": abs(cogs) if cogs < 0 else 0,
				"remarks": f"Net COGS for period ending {self.posting_date}",
			})

		self.remarks = (
			f"Periodic Accounting Entry — {self.posting_date}\n"
			+ "\n".join(log_lines)
		)

		# Sanity check
		total_dr = sum(flt(r.debit) for r in self.accounts)
		total_cr = sum(flt(r.credit) for r in self.accounts)
		if abs(total_dr - total_cr) > 0.01:
			frappe.throw(
				_(f"Entry does not balance: Dr {total_dr:.3f} ≠ Cr {total_cr:.3f}. "
				  "Please check purchases GL and stock accounts.")
			)

		if not self.accounts:
			frappe.msgprint(_("No purchases or stock movement found for this period. Nothing to post."), indicator="orange")
		else:
			frappe.msgprint(
				_(
					"Balance calculated. Purchases: {0} | Closing Stock: {1} | Net COGS: {2}. "
					"Review the accounts table and Submit."
				).format(
					frappe.bold(f"{total_purchases:.3f}"),
					frappe.bold(f"{total_net_change:.3f}"),
					frappe.bold(f"{cogs:.3f}"),
				),
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
			# Only include accounts that have at least one warehouse mapped to them.
			# get_stock_and_account_balance() derives Bin value from warehouse→account links,
			# so stock-typed accounts with no warehouse (e.g. Stock In Transit holding account)
			# would return a fallback company-total Bin and cause double-counting.
			return frappe.db.sql_list("""
				SELECT DISTINCT w.account
				FROM `tabWarehouse` w
				WHERE w.company = %s AND w.account IS NOT NULL AND w.account != ''
			""", self.company)
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
