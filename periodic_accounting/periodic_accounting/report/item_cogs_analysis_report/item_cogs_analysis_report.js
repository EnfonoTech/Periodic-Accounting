frappe.query_reports["Item COGS Analysis Report"] = {
	"filters": [
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
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: function () {
				return { filters: { company: frappe.query_report.get_filter_value("company") } };
			},
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: function () {
				return { filters: { company: frappe.query_report.get_filter_value("company") } };
			},
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: function () {
				const ig = frappe.query_report.get_filter_value("item_group");
				return ig ? { filters: { item_group: ig } } : {};
			},
		},
		{
			fieldname: "hide_zero_variance",
			label: __("Hide Fully-Zero Rows"),
			fieldtype: "Check",
			default: 0,
		},
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		const fn = column.fieldname;
		const rt = data._row_type || "";

		// ── TOTAL row — plain bold ────────────────────────────────────────────
		if (rt === "total") {
			return `<strong>${value || ""}</strong>`;
		}

		// ── Variance column ───────────────────────────────────────────────────
		if (fn === "variance") {
			const v = parseFloat(data.variance) || 0;
			if (Math.abs(v) < 0.005) {
				return `<span style="color:#2e7d32;font-weight:700">✓ ${value}</span>`;
			}
			return `<span style="background:#c62828;color:#fff;padding:2px 8px;` +
			       `border-radius:4px;font-weight:700">⚠ ${value}</span>`;
		}

		// ── COGS Difference column ────────────────────────────────────────────
		if (fn === "cogs_diff") {
			const v = parseFloat(data.cogs_diff) || 0;
			if (Math.abs(v) < 0.005) {
				return `<span style="color:#2e7d32;font-weight:700">✓ ${value}</span>`;
			}
			return `<span style="background:#e65100;color:#fff;padding:2px 8px;` +
			       `border-radius:4px;font-weight:700">△ ${value}</span>`;
		}

		// ── Sales COGS — key column: accent highlight ─────────────────────────
		if (fn === "sales_cogs") {
			const v = parseFloat(data.sales_cogs) || 0;
			if (v > 0.005) {
				return `<span style="color:#c62828;font-weight:700">${value}</span>`;
			}
			return `<span style="color:#9e9e9e">${value}</span>`;
		}

		// ── Closing stock column ──────────────────────────────────────────────
		if (fn === "closing") {
			const v = parseFloat(data.closing) || 0;
			if (v > 0.005) {
				return `<span style="color:#1565c0;font-weight:600">${value}</span>`;
			}
			return value;
		}

		// ── Opening stock column ──────────────────────────────────────────────
		if (fn === "opening") {
			const v = parseFloat(data.opening) || 0;
			if (v > 0.005) {
				return `<span style="color:#4527a0;font-weight:600">${value}</span>`;
			}
			return value;
		}

		// ── Purchase columns: shade non-zero ──────────────────────────────────
		if (["local_pr", "import_pr", "lcv", "pi_adj"].includes(fn)) {
			const v = parseFloat(data[fn]) || 0;
			if (v > 0.005) {
				return `<span style="color:#1b5e20;font-weight:600">${value}</span>`;
			}
			return `<span style="color:#bdbdbd">${value || "—"}</span>`;
		}

		// ── Transfer/Mfg columns: grey when zero ─────────────────────────────
		if (["t_in", "t_out", "mfg_out", "pur_ret", "sales_ret_in"].includes(fn)) {
			const v = parseFloat(data[fn]) || 0;
			if (!v || Math.abs(v) < 0.005) {
				return `<span style="color:#bdbdbd">—</span>`;
			}
		}

		return value;
	},

	"get_datatable_options": function (options) {
		options.freezeColumnsAt = 3;
		return options;
	},
};
