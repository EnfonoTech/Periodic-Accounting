// Shared ERPNext-style formatter for all Periodic Accounting financial reports.
// Included globally via hooks.py app_include_js.

function periodic_accounting_formatter(value, row, column, data, default_formatter) {
	if (!data || Object.keys(data).length === 0) return "";

	const rowType = data._row_type || "detail";
	const isGroup = data.is_group;
	const pad     = (data.indent || 0) * 20;
	const style   = `padding-left:${pad}px;`;

	// ── % of Net Sales column ────────────────────────────────────────────────
	if (column.fieldname === "pct") {
		if (data.pct === null || data.pct === undefined) return "";
		value = default_formatter(value, row, column, data);
		if (rowType === "net_profit") {
			const c = (data.amount || 0) >= 0 ? "var(--green-600)" : "var(--red-600)";
			return `<strong><span style="color:${c}">${value}</span></strong>`;
		}
		if (rowType === "gross_profit") {
			return `<strong><span style="color:var(--blue-600)">${value}</span></strong>`;
		}
		if (rowType === "section_total" || isGroup) {
			return `<strong>${value}</strong>`;
		}
		return value;
	}

	// ── Amount column ────────────────────────────────────────────────────────
	if (column.fieldname === "amount") {
		if (data.amount === null || data.amount === undefined) return "";
		value = default_formatter(value, row, column, data);

		if (rowType === "net_profit" || rowType === "gross_profit" || rowType === "section_total") {
			value = `<strong>${value}</strong>`;
		}
		if (rowType === "net_profit") {
			const c = (data.amount || 0) >= 0 ? "var(--green-600)" : "var(--red-600)";
			value = `<span style="color:${c}">${value}</span>`;
		} else if (rowType === "gross_profit") {
			value = `<span style="color:var(--blue-600)">${value}</span>`;
		} else if ((data.amount || 0) < 0) {
			value = `<span style="color:var(--red-500)">${value}</span>`;
		}
		return value;
	}

	// ── Account / Particulars column ─────────────────────────────────────────
	if (column.fieldname === "account") {
		if (!value) return "";

		if (rowType === "note") {
			return `<span style="color:var(--text-muted); font-size:0.9em;">${value}</span>`;
		}

		if (rowType === "section_header") {
			return `<span style="color:var(--text-muted); font-size:0.8em;
			              letter-spacing:0.08em; text-transform:uppercase;
			              font-weight:600;">${value}</span>`;
		}

		if (rowType === "balance_check") {
			const c = data._balanced ? "var(--green-600)" : "var(--red-600)";
			return `<span style="color:${c}; font-style:italic;">${value}</span>`;
		}

		if (isGroup) {
			let extra = "";
			if (rowType === "net_profit")   extra = `color:${(data.amount||0)>=0?"var(--green-600)":"var(--red-600)"};`;
			if (rowType === "gross_profit") extra = "color:var(--blue-600);";
			// Group rows can also be drill-down links (e.g. Net COGS → Sales Stock Entries)
			if (data.link) {
				return `<a href="${data.link}" target="_blank"
				           style="${style} font-weight:bold; ${extra} text-decoration:underline;
				                  text-underline-offset:3px; text-decoration-style:dotted;"
				           title="Click to view detail">${value}</a>`;
			}
			return `<strong style="${style} ${extra}">${value}</strong>`;
		}

		// SLE-tagged rows: blue badge on the display name
		if (value.includes("← SLE")) {
			const plain = value.replace("← SLE", "").trim();
			const inner = `${plain} <span style="color:var(--blue-600); font-size:0.8em; font-weight:500;">← SLE</span>`;
			if (data.link) {
				return `<a href="${data.link}" target="_blank"
				           style="${style} color:var(--text-color); text-decoration:underline;
				                  text-underline-offset:3px; text-decoration-style:dotted;"
				           title="Click to view Stock Balance">${inner}</a>`;
			}
			return `<span style="${style}">${inner}</span>`;
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
