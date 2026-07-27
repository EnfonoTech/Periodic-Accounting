// periodic_accounting/periodic_accounting/report/trading_reconciliation_detail/trading_reconciliation_detail.js
// The documents behind each "Reconciliation to Trial Balance" line in the Audit Trading Account
// Report. Head totals come from that report's own helpers, so the two cannot disagree.

frappe.query_reports["Trading Reconciliation Detail"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "head",
			label: __("Reconciliation Head"),
			fieldtype: "Select",
			default: "All",
			options: [
				"All",
				"Sales valuation drift",
				"Non-stock / Non-sales COGS postings",
				"Received vs Billed (SRBNB)",
				"Stock Entries / Transfers",
				"Stock Reconciliation vs GL",
			].join("\n"),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		// a head line is the total being explained; its detail rows sit under it
		if (data.is_group) {
			value = `<span style="font-weight:700">${value}</span>`;
		}
		if (column.fieldname === "difference" && data.difference) {
			const colour = data.difference > 0 ? "var(--red-500)" : "var(--green-600)";
			value = `<span style="color:${colour}">${value}</span>`;
		}
		if (column.fieldname === "reason") {
			value = `<span style="color:var(--text-muted)">${value}</span>`;
		}
		return value;
	},

	onload: function (report) {
		report.page.add_inner_button(__("Audit Trading Account Report"), function () {
			const f = report.get_values();
			frappe.set_route("query-report", "Audit Trading Account Report", {
				company: f.company,
				from_date: f.from_date,
				to_date: f.to_date,
			});
		});
	},
};
