frappe.query_reports["Purchase Stock Entries"] = {
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
			options: "Warehouse"
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center"
		},
		{
			fieldname: "purchase_type",
			label: __("Purchase Type"),
			fieldtype: "Select",
			options: "\nLocal\nImport\nLanded Cost\nReturns",
			default: ""
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		if (!data || Object.keys(data).length === 0) return "";
		const rowType = data._row_type;

		value = default_formatter(value, row, column, data);

		if (rowType === "total") {
			// Grand total: bold + blue accent on the label column
			if (column.fieldname === "voucher_type") {
				return `<strong style="color:var(--blue-600);">${value}</strong>`;
			}
			return value ? `<strong style="color:var(--blue-600);">${value}</strong>` : "";
		}

		if (rowType === "subtotal") {
			if (column.fieldname === "voucher_type") {
				return `<strong style="color:var(--text-muted); font-size:0.9em;">${value}</strong>`;
			}
			// Bold the numeric columns for subtotals
			const numericFields = ["qty_in", "qty_out", "stock_value_difference"];
			if (numericFields.includes(column.fieldname) && value) {
				return `<strong>${value}</strong>`;
			}
			return value || "";
		}

		return value;
	}
};
