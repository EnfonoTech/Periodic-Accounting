// periodic_accounting/public/js/company_stock_account_filters.js
//
// ERPNext restricts two Company fields to a single account_type through a link query on the
// form — Stock Adjustment Account to `root_type: Expense, account_type: Stock Adjustment`, and
// Stock Received But Not Billed to `root_type: Liability, account_type: Stock Received But Not
// Billed` (erpnext/setup/doctype/company/company.js, inside the perpetual-inventory block).
// Nothing on the server enforces either: Company.validate_default_accounts checks only that the
// account belongs to the company and matches its currency.
//
// Steel Force want to point both at Cost of Goods Sold, so the pickers are widened here to any
// non-group account of the company. This is a deliberate local relaxation of an ERPNext guard,
// and the guard exists for a reason:
//
//   * Stock Received But Not Billed is a goods-received-not-invoiced ACCRUAL. Typed as an
//     expense it stops appearing on the balance sheet, and Period Closing Voucher sweeps any
//     open balance into retained earnings — so an un-invoiced receipt is booked as profit in
//     one year and charged again as cost in the next, with nothing left to reverse.
//   * Stock Adjustment posts write-downs, shrinkage and revaluations. Merged into Cost of Goods
//     Sold they can no longer be told apart from the cost of goods actually sold.
//
// Both consequences were demonstrated on UAT before this was written. The filters are widened,
// not removed silently: a warning is shown the moment either field is pointed somewhere ERPNext
// would not have allowed, so nobody changes it without knowing.

frappe.ui.form.on("Company", {
	onload(frm) {
		// any account of this company, group accounts excluded — the two account_type
		// restrictions ERPNext applies are dropped
		["stock_adjustment_account", "stock_received_but_not_billed"].forEach((field) => {
			frm.set_query(field, () => ({
				filters: { company: frm.doc.company_name || frm.doc.name, is_group: 0 },
			}));
		});
	},

	stock_received_but_not_billed(frm) {
		_pa_warn_if_not(frm, "stock_received_but_not_billed", "Liability", __(
			"Stock Received But Not Billed is an accrual for goods received but not yet invoiced. " +
			"On a Profit and Loss account the balance is swept into retained earnings at period " +
			"close, so the accrual cannot reverse when the supplier invoice arrives."
		));
	},

	stock_adjustment_account(frm) {
		_pa_warn_if_not(frm, "stock_adjustment_account", "Expense", __(
			"Stock Adjustment carries write-downs, shrinkage and revaluations. Pointing it at " +
			"Cost of Goods Sold merges those into the cost of goods actually sold, and they can " +
			"no longer be reported separately."
		));
	},
});

function _pa_warn_if_not(frm, field, expected_root, message) {
	const account = frm.doc[field];
	if (!account) return;

	frappe.db.get_value("Account", account, ["root_type", "account_type"]).then((r) => {
		const value = r && r.message;
		if (!value) return;
		if (value.root_type === expected_root) return;

		frappe.msgprint({
			title: __("Non-standard account for {0}", [frappe.meta.get_label("Company", field, frm.doc.name)]),
			indicator: "orange",
			message:
				__("{0} is a {1} account. ERPNext expects a {2} account here.", [
					frappe.bold(account),
					frappe.bold(value.root_type),
					frappe.bold(expected_root),
				]) +
				"<br><br>" +
				message,
		});
	});
}
