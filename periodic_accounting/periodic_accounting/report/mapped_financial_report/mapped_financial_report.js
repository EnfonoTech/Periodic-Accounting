frappe.query_reports["Mapped Financial Report"] = {
	filters: [
		{
			fieldname: "mapper",
			label: __("Report Mapper"),
			fieldtype: "Link",
			options: "Report Mapper",
			reqd: 1,
			on_change: function () {
				var mapper = frappe.query_report.get_filter_value("mapper");
				if (!mapper) return;
				frappe.db.get_doc("Report Mapper", mapper).then(function (doc) {
					if (doc.company) {
						frappe.query_report.set_filter_value("company", doc.company);
					}
					if (doc.period_mode) {
						frappe.query_report.set_filter_value("period_mode", doc.period_mode);
					}
				});
			},
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "period_mode",
			label: __("Period Mode"),
			fieldtype: "Select",
			options: "Period\nYTD",
			default: "Period",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname !== "label" || !data) {
			return default_formatter(value, row, column, data);
		}

		var rendered = frappe.utils.escape_html(value || "");

		if (data.is_bold) {
			rendered = "<strong>" + rendered + "</strong>";
		}
		if (data.is_italic) {
			rendered = "<em>" + rendered + "</em>";
		}

		if (data.indent) {
			rendered =
				'<span style="padding-left:' +
				data.indent * 20 +
				'px">' +
				rendered +
				"</span>";
		}

		return rendered;
	},
};
