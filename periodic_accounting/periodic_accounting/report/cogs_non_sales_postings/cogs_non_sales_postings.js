frappe.query_reports["COGS Non-Sales Postings"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1, default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" }
	],
	formatter: function (value, row, column, data, default_formatter) {
		if (!data || Object.keys(data).length === 0) return "";
		const rt = data._row_type;
		value = default_formatter(value, row, column, data);
		if (rt === "total") {
			return value ? `<strong style="color:var(--blue-600);">${value}</strong>` : "";
		}
		if (rt === "subtotal") {
			if (column.fieldname === "voucher_type") return `<strong style="color:var(--text-muted); font-size:0.9em;">${value}</strong>`;
			if (["debit", "credit", "net"].includes(column.fieldname) && value) return `<strong>${value}</strong>`;
			return value || "";
		}
		return value;
	}
};
