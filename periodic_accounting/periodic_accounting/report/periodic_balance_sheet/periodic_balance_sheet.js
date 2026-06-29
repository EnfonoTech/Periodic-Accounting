frappe.query_reports["Periodic Balance Sheet"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company")
		},
		{
			fieldname: "from_date",
			label: __("From Date (P&L Period Start)"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.year_start(),
			description: __("Start of the P&L period — used to compute Net Profit for the current year.")
		},
		{
			fieldname: "to_date",
			label: __("As of Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
			description: __("Account balances and SLE stock computed as of this date.")
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			description: __("Restrict SLE stock to a specific warehouse. Overrides Cost Center filter.")
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Filter GL entries and SLE by cost centre.")
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		return periodic_accounting_formatter(value, row, column, data, default_formatter);
	},

	onload: function(report) {
		function get_nav_params() {
			return {
				company:     report.get_filter_value("company"),
				from_date:   report.get_filter_value("from_date"),
				to_date:     report.get_filter_value("to_date"),
				warehouse:   report.get_filter_value("warehouse")   || undefined,
				cost_center: report.get_filter_value("cost_center") || undefined,
			};
		}
		const grp = __("Financial Statements");
		report.page.add_inner_button(__("Trading Account"), function() {
			frappe.set_route("query-report", "Realtime Trading Account Report", get_nav_params());
		}, grp);
		report.page.add_inner_button(__("Gross & Net Profit"), function() {
			frappe.set_route("query-report", "Periodic Gross and Net Profit", get_nav_params());
		}, grp);
	},
};
