frappe.query_reports["Realtime Trading Account Report"] = {
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
	],

	onload: function (report) {
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
		report.page.add_inner_button(__("Gross & Net Profit"), function () {
			frappe.set_route("query-report", "Periodic Gross and Net Profit", get_nav_params());
		}, grp);
		report.page.add_inner_button(__("Balance Sheet"), function () {
			frappe.set_route("query-report", "Periodic Balance Sheet", get_nav_params());
		}, grp);
		report.page.add_inner_button(__("Cash Flow"), function () {
			frappe.set_route("query-report", "Standard Cash Flow Report", get_nav_params());
		}, grp);
	},

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		const fn = column.fieldname;
		const rt = data._row_type || "detail";

		// ── Primary section headers (SALES / COST OF GOODS SOLD) ─────────────
		if (rt === "section") {
			if (fn === "particulars") {
				return `<strong style="color:#1a237e;font-size:12px;letter-spacing:.04em">${value}</strong>`;
			}
			return "";
		}

		// ── Secondary section headers (Breakdown by…) ────────────────────────
		if (rt === "recon_header") {
			if (fn === "particulars") {
				const clean = (data.particulars || "").replace(/^── /, "").replace(/ ─+$/, "");
				return `<strong style="color:#455a64">${clean}</strong>`;
			}
			return "";
		}

		// ── Warehouse / Item Group sub-headers ───────────────────────────────
		if (rt === "wh_header" && fn === "particulars") {
			return `<span style="color:#1565c0;font-weight:700">▸ ${value}</span>`;
		}

		// ── NET SALES ────────────────────────────────────────────────────────
		if (rt === "net_sales") {
			return `<strong style="color:#00695c">${value}</strong>`;
		}

		// ── NET COGS ─────────────────────────────────────────────────────────
		if (rt === "net_cogs") {
			const inner = `<strong style="color:#bf360c">${value}</strong>`;
			if (fn === "particulars" && data.link) {
				return `<a href="${data.link}" title="Click to view item outflow (Sales Invoice + Delivery Note)"
				           style="text-decoration:underline dotted; text-underline-offset:3px;">${inner}</a>`;
			}
			return inner;
		}

		// ── GROSS PROFIT ─────────────────────────────────────────────────────
		if (rt === "gross_profit") {
			const profit = (parseFloat(data.credit) || 0) > 0.005;
			const color  = profit ? "#1b5e20" : "#b71c1c";
			return `<strong style="color:${color};font-size:13px">${value}</strong>`;
		}

		// ── Variance row (Formula COGS vs GL COGS — the truthful-mirror check) ─
		if (rt === "variance") {
			const dr    = parseFloat(data.debit)  || 0;
			const cr    = parseFloat(data.credit) || 0;
			const dirty = (dr + cr) > 0.005;

			if (fn === "particulars") {
				const icon  = dirty ? "❌" : "✅";
				const color = dirty ? "#b71c1c" : "#2e7d32";
				const label = `${icon} <span style="color:${color};font-weight:600">${value}</span>`;
				if (dirty && data.link) {
					return `<a href="${data.link}" title="Click to investigate"
					           style="text-decoration:none">${label}</a>`;
				}
				return label;
			}
			if (fn === "debit" || fn === "credit") {
				if (!dirty) return `<span style="color:#2e7d32;font-weight:600">${value}</span>`;
				return `<strong style="color:#b71c1c">${value}</strong>`;
			}
		}

		// ── Empty divider rows ────────────────────────────────────────────────
		if (rt === "divider") return "";

		// ── Clickable particulars (any detail row with a link) ─────────────────
		if (fn === "particulars" && data.link) {
			return `<a href="${data.link}" title="Click to view detail"
			           style="color:inherit;text-decoration:underline dotted">${value}</a>`;
		}

		return value;
	},
};
