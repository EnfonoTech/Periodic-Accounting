frappe.query_reports["Landed Cost Voucher Drill"] = {
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
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		if (!data || Object.keys(data).length === 0) return "";
		const rt = data._row_type;

		value = default_formatter(value, row, column, data);

		if (rt === "total") {
			return value ? `<strong style="color:var(--blue-600);">${value}</strong>` : "";
		}

		if (rt === "subtotal") {
			if (column.fieldname === "lcv_name") {
				return `<span style="color:var(--text-muted);font-size:0.9em;">${value}</span>`;
			}
			if (column.fieldname === "amount") {
				return `<strong>${value}</strong>`;
			}
			return value || "";
		}

		if (rt === "source") {
			if (column.fieldname === "lcv_name" || column.fieldname === "posting_date") {
				return `<span style="color:var(--text-muted);">${value}</span>`;
			}
			if (column.fieldname === "src_doc") {
				return value ? `<span style="color:var(--blue-500);">${value}</span>` : "";
			}
			return value || "";
		}

		if (rt === "charge") {
			if (column.fieldname === "amount") {
				return `<strong style="color:var(--orange-600);">${value}</strong>`;
			}
			return value || "";
		}

		return value;
	}
};
