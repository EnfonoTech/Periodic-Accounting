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

const PA_WIDENED_FIELDS = ["stock_adjustment_account", "stock_received_but_not_billed"];

// erpnext's own company.js is loaded AFTER this file (hooks order puts the app's doctype_js
// first), so its set_query runs last and would put the account_type filters straight back.
// Re-applying on the next tick lands after every synchronous handler of the same event.
function pa_widen_account_queries(frm) {
	PA_WIDENED_FIELDS.forEach((field) => {
		if (!frm.fields_dict[field]) return;
		frm.set_query(field, () => ({
			filters: { company: frm.doc.company_name || frm.doc.name, is_group: 0 },
		}));
	});
}

// Re-applying set_query is not enough on its own: erpnext calls setup_queries(frm) from its
// own refresh handler (company.js:99), so its filters go back on every single render of the
// form. The helper that installs them is patched instead — once, lazily, because this file is
// parsed before erpnext's — so for these two fields the account_type restriction is simply
// never installed, whoever calls it and whenever.
function pa_patch_erpnext_query_helper() {
	if (!window.erpnext || !erpnext.company || !erpnext.company.set_custom_query) return;
	if (erpnext.company.set_custom_query.__pa_widened) return;

	const original = erpnext.company.set_custom_query;
	const patched = function (frm, v) {
		if (v && PA_WIDENED_FIELDS.includes(v[0])) {
			frm.set_query(v[0], () => ({
				filters: { company: frm.doc.name, is_group: 0 },
			}));
			return;
		}
		return original.apply(this, arguments);
	};
	patched.__pa_widened = true;
	erpnext.company.set_custom_query = patched;
}

function pa_widen_soon(frm) {
	pa_patch_erpnext_query_helper();
	pa_widen_account_queries(frm);
	setTimeout(() => {
		pa_patch_erpnext_query_helper();
		pa_widen_account_queries(frm);
	}, 0);
}

frappe.ui.form.on("Company", {
	onload(frm) {
		pa_widen_soon(frm);
	},

	refresh(frm) {
		pa_widen_soon(frm);
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
