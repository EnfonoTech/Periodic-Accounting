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
			options: "Warehouse",
			description: __("Filter by a specific warehouse. Overrides Cost Center warehouse filter.")
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			description: __("Filters SLE by warehouses linked to this cost centre.")
		}
	],

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
		report.page.add_inner_button(__("Gross & Net Profit"), function() {
			frappe.set_route("query-report", "Periodic Gross and Net Profit", get_nav_params());
		}, grp);
		report.page.add_inner_button(__("Balance Sheet"), function() {
			frappe.set_route("query-report", "Periodic Balance Sheet", get_nav_params());
		}, grp);
	},

	formatter: function(value, row, column, data, default_formatter) {
		if (!data) return default_formatter(value, row, column, data);

		// Dr / Cr amount columns
		if (column.fieldname === "debit" || column.fieldname === "credit") {
			value = default_formatter(value, row, column, data);
			const isTotal = data.particulars && data.particulars.startsWith("TOTAL");
			if (isTotal) return `<strong style="color:var(--blue-600);">${value}</strong>`;
			return data.bold ? `<strong>${value}</strong>` : value;
		}

		// Particulars column
		if (column.fieldname === "particulars") {
			if (!value) return "";
			const pad   = (data.indent || 0) * 20;
			const style = `display:inline-block; padding-left:${pad}px;`;

			// Separator line row
			if (value.startsWith("─")) {
				return `<span style="color:var(--border-color); letter-spacing:-1px;">${value}</span>`;
			}

			// Margin analysis note row
			if (value.startsWith("Gross Margin:")) {
				return `<span style="color:var(--text-muted); font-size:0.9em; font-style:italic;">${value}</span>`;
			}

			// Balance verification row
			if (value.startsWith("TOTAL")) {
				return `<strong style="${style} color:var(--blue-600);">${value}</strong>`;
			}

			if (data.bold) {
				if (data.link) {
					return `<a href="${data.link}" target="_blank"
					           style="${style} font-weight:bold; letter-spacing:0.04em;
					                  color:var(--text-color); text-decoration:underline;
					                  text-underline-offset:3px; text-decoration-style:dotted;"
					           title="Click to view detail">${value}</a>`;
				}
				return `<strong style="${style} letter-spacing:0.04em;">${value}</strong>`;
			}
			if (data.link) {
				return `<a href="${data.link}" target="_blank"
				           style="${style} color:var(--text-color); text-decoration:underline;
				                  text-underline-offset:3px; text-decoration-style:dotted;"
				           title="Click to view detail">${value}</a>`;
			}
			return `<span style="${style}">${value}</span>`;
		}

		return default_formatter(value, row, column, data);
	}
};
