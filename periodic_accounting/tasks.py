import frappe


def auto_periodic_stock_reconciliation():
	"""
	Runs on last day of month at 23:30.
	Creates and submits Periodic Stock Reconciliation
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
					title=f"PSR Skipped — {company}",
					message=(
						"Stock Adjustment account not found. "
						"Create under COGS with account_type = Cost of Goods Sold."
					),
				)
				continue

			psr = frappe.new_doc("Periodic Stock Reconciliation")
			psr.company = company
			psr.posting_date = get_last_day(today())
			psr.for_all_stock_accounts = 1
			psr.difference_account = diff_account

			psr.get_balance()

			if not psr.accounts:
				frappe.logger().info(f"No stock difference for {company} — PSR skipped")
				continue

			psr.insert(ignore_permissions=True)
			psr.submit()

			frappe.logger().info(f"PSR {psr.name} submitted for {company}")
			frappe.db.commit()

		except Exception:
			frappe.log_error(
				title=f"PSR Auto-Run Failed — {company}",
				message=frappe.get_traceback(),
			)
			frappe.db.rollback()
