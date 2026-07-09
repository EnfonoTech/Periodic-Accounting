frappe.query_reports["Periodic Gross and Net Profit"] = {
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
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start()
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			description: __("Filter stock (SLE) by a specific warehouse. Overrides Cost Center warehouse filter.")
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Filters GL entries by cost centre; filters SLE by warehouses linked to this cost centre.")
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
				warehouse:   report.get_filter_value("warehouse")    || undefined,
				cost_center: report.get_filter_value("cost_center")  || undefined,
			};
		}
		const grp = __("Financial Statements");
		report.page.add_inner_button(__("Trading Account"), function() {
			frappe.set_route("query-report", "Realtime Trading Account Report", get_nav_params());
		}, grp);
		report.page.add_inner_button(__("Balance Sheet"), function() {
			frappe.set_route("query-report", "Periodic Balance Sheet", get_nav_params());
		}, grp);
		report.page.add_inner_button(__("Cash Flow"), function() {
			frappe.set_route("query-report", "Standard Cash Flow Report", get_nav_params());
		}, grp);
	},
};
