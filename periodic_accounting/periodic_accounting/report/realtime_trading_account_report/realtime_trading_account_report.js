frappe.query_reports["Realtime Trading Account Report"] = {
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
		if (!data) return default_formatter(value, row, column, data);

		// ── Amount columns: bold totals ───────────────────────────────────
		if (column.fieldname === "debit" || column.fieldname === "credit") {
			value = default_formatter(value, row, column, data);
			if (data.bold) {
				return `<strong>${value}</strong>`;
			}
			return value;
		}

		// ── Particulars column ────────────────────────────────────────────
		if (column.fieldname === "particulars") {
			if (!value) return "";

			let pad   = (data.indent || 0) * 20;
			let style = `display:inline-block; padding-left:${pad}px;`;

			if (data.bold) {
				return `<strong style="${style} letter-spacing:0.04em;">${value}</strong>`;
			}

			if (data.link) {
				return `<a href="${data.link}"
				           target="_blank"
				           style="${style} color:var(--text-color); text-decoration:underline;
				                  text-underline-offset:3px; text-decoration-style:dotted;
				                  cursor:pointer;"
				           title="Click to view detail">${value}</a>`;
			}

			return `<span style="${style}">${value}</span>`;
		}

		return default_formatter(value, row, column, data);
	}
};
