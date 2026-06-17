import frappe


def auto_periodic_accounting_entry():
	"""
	Runs on last day of month at 23:30.
	Creates and submits a Periodic Accounting Entry
	for all companies with perpetual inventory disabled.
	"""
	from frappe.utils import get_last_day, today

	companies = frappe.get_all(
		"Company",
		filters={"enable_perpetual_inventory": 0},
		pluck="name",
	)

	for company in companies:
		try:
			diff_account = frappe.db.get_value(
				"Account",
				{
					"company": company,
					"account_name": ("like", "%Stock Adjustment%"),
					"account_type": "Cost of Goods Sold",
					"is_group": 0,
				},
				"name",
			)

			if not diff_account:
				frappe.log_error(
					title=f"PAE Skipped — {company}",
					message=(
						"Stock Adjustment account not found. "
						"Create under COGS with account_type = Cost of Goods Sold."
					),
				)
				continue

			pae = frappe.new_doc("Periodic Accounting Entry")
			pae.company = company
			pae.posting_date = get_last_day(today())
			pae.for_all_stock_accounts = 1
			pae.difference_account = diff_account

			pae.get_balance()

			if not pae.accounts:
				frappe.logger().info(f"No stock difference for {company} — PAE skipped")
				continue

			pae.insert(ignore_permissions=True)
			pae.submit()

			frappe.logger().info(f"PAE {pae.name} submitted for {company}")
			frappe.db.commit()

		except Exception:
			frappe.log_error(
				title=f"PAE Auto-Run Failed — {company}",
				message=frappe.get_traceback(),
			)
			frappe.db.rollback()
