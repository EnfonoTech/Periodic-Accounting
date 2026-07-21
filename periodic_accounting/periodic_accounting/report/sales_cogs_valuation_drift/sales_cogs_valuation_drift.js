frappe.query_reports["Sales COGS Valuation Drift"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" }
	],
	formatter: function (value, row, column, data, default_formatter) {
		if (!data || Object.keys(data).length === 0) return "";
		const rt = data._row_type;
		value = default_formatter(value, row, column, data);
		if (rt === "total") {
			return value ? `<strong style="color:var(--blue-600);">${value}</strong>` : "";
		}
		if (column.fieldname === "drift" && data.drift) {
			const neg = parseFloat(data.drift) < 0;
			return `<span style="color:${neg ? 'var(--red-600)' : 'var(--orange-600)'};font-weight:600;">${value}</span>`;
		}
		return value;
	}
};
