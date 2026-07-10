frappe.query_reports["Purchase Invoice Stocked Items"] = {
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
			fieldname: "transaction",
			label: __("Transaction Type"),
			fieldtype: "Select",
			options: "All\nPurchases\nReturns",
			default: "All"
		},
		{
			fieldname: "currency_type",
			label: __("Currency"),
			fieldtype: "Select",
			options: "All\nLocal\nImport",
			default: "All"
		}
	],

	formatter: function(value, row, column, data, default_formatter) {
		if (!data || Object.keys(data).length === 0) return "";
		const rowType = data._row_type;

		value = default_formatter(value, row, column, data);

		// ── Grand total row ────────────────────────────────────────────────────
		if (rowType === "total") {
			if (!value) return "";
			return `<strong style="color:var(--blue-600);">${value}</strong>`;
		}

		// ── PI subtotal row ────────────────────────────────────────────────────
		if (rowType === "subtotal") {
			if (!value) return "";
			const numericFields = ["qty", "base_net_amount"];
			if (numericFields.includes(column.fieldname)) {
				return `<strong>${value}</strong>`;
			}
			if (column.fieldname === "purchase_invoice") {
				return `<span style="color:var(--text-muted); font-size:0.9em;">${value}</span>`;
			}
			if (column.fieldname === "txn_type") {
				return _typeChip(data.txn_type, value);
			}
			return value;
		}

		// ── Detail row ────────────────────────────────────────────────────────
		if (column.fieldname === "txn_type") {
			return _typeChip(data.txn_type, value);
		}

		return value;
	}
};

function _typeChip(typeStr, rendered) {
	if (!typeStr) return rendered || "";
	const isReturn = typeStr.includes("Return");
	const isImport = typeStr.includes("Import");
	const noStock  = typeStr.includes("no stock update");

	let color = "var(--green-500)";
	if (isReturn)      color = "var(--red-500)";
	else if (isImport) color = "var(--orange-500)";

	const opacity = noStock ? "0.7" : "1";
	return `<span style="color:${color}; opacity:${opacity}; font-weight:500;">${rendered}</span>`;
}
