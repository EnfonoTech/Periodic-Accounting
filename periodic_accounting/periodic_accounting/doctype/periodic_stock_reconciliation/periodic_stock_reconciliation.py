import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt
from erpnext.accounts.utils import get_stock_and_account_balance


class PeriodicStockReconciliation(Document):

	def validate(self):
		self.validate_company()
		self.validate_accounts()

	def validate_company(self):
		if frappe.db.get_value("Company", self.company, "enable_perpetual_inventory"):
			frappe.throw(
				_(
					"Periodic Stock Reconciliation is only for companies with "
					"Perpetual Inventory DISABLED. Company {0} has perpetual "
					"inventory enabled. Use standard ERPNext for COGS tracking."
				).format(frappe.bold(self.company))
			)

	def validate_accounts(self):
		if not self.difference_account:
			frappe.throw(_("Please select a Difference Account (COGS)."))
		if not self.for_all_stock_accounts and not self.stock_account:
			frappe.throw(_("Please select a Stock Account or tick 'For All Stock Accounts'."))

	def on_submit(self):
		self.create_journal_entry()

	def on_cancel(self):
		self.cancel_journal_entry()

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
			account_bal, stock_bal, _ = get_stock_and_account_balance(
				account, self.posting_date, self.company
			)

			# positive → stock > GL: recognise closing stock (Dr Stock / Cr COGS)
			# negative → stock < GL: reduce stock (Cr Stock / Dr COGS)
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
						f"Stock reconciliation as at {self.posting_date} | "
						f"GL: {account_bal:.3f} | Stock Reg: {stock_bal:.3f}"
					),
				},
			)

			diff_account_name = frappe.db.get_value(
				"Account", self.difference_account, "account_name"
			)

			self.append(
				"accounts",
				{
					"account": self.difference_account,
					"account_name": diff_account_name,
					"debit": abs(difference) if difference < 0 else 0,
					"credit": difference if difference > 0 else 0,
					"remarks": f"Offset for {account_name} periodic reconciliation",
				},
			)

		self.remarks = (
			f"Periodic Stock Reconciliation — {self.posting_date}\n"
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

	def get_stock_accounts(self):
		if self.for_all_stock_accounts:
			return frappe.get_all(
				"Account",
				filters={
					"company": self.company,
					"account_type": "Stock",
					"root_type": "Asset",
					"is_group": 0,
				},
				pluck="name",
			)
		return [self.stock_account]

	def create_journal_entry(self):
		if not self.accounts:
			frappe.throw(_("No accounts to post. Click 'Get Balance' first."))

		je = frappe.new_doc("Journal Entry")
		je.voucher_type = "Journal Entry"
		je.posting_date = self.posting_date
		je.company = self.company
		je.user_remark = (
			f"[PERIODIC STOCK RECONCILIATION] {self.name} | "
			f"Auto-generated entry as at {self.posting_date}"
		)

		for row in self.accounts:
			je_row = {
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

		self.db_set("journal_entry", je.name)

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
			self.db_set("journal_entry", None)
