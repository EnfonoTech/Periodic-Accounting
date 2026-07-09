frappe.query_reports["Standard Cash Flow Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
		},
		{
			fieldname: "period_start_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "period_end_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "Link",
			options: "Cost Center",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "include_default_book_entries",
			label: __("Include Default FB Entries"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "show_opening_and_closing_balance",
			label: __("Show Opening and Closing Balance"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "show_account_breakup",
			label: __("Show Account Breakup"),
			fieldtype: "Check",
			default: 1,
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname === "account") {
			var display = frappe.utils.escape_html(value || "");

			// Section headers and total rows — bold, not clickable
			if (data && data.is_group) {
				return "<b>" + display + "</b>";
			}

			// Blank spacer rows
			if (!display) return "";

			// Net Profit row → P&L report
			if (data && data._link_type === "profit_loss") {
				return "<span class='cf-drill' data-link-type='profit_loss'"
					+ " style='cursor:pointer;color:var(--primary,#4c85e7);text-decoration:underline;'>"
					+ display + "</span>";
			}

			// All other line rows — clickable, with or without mapped accounts
			var enc = (data && data._accounts && data._accounts.length)
				? encodeURIComponent(JSON.stringify(data._accounts))
				: "";

			// Account-breakup child rows (TB-style) — muted, click → GL for that account
			if (data && data._breakup) {
				return "<span class='cf-drill'"
					+ (enc ? " data-enc='" + enc + "'" : "")
					+ " style='cursor:pointer;color:var(--text-muted,#74808b);"
					+ "text-decoration:underline dotted;font-size:0.95em;'>"
					+ display + "</span>";
			}

			return "<span class='cf-drill'"
				+ (enc ? " data-enc='" + enc + "'" : "")
				+ " style='cursor:pointer;color:var(--primary,#4c85e7);text-decoration:underline;'>"
				+ display + "</span>";
		}

		if (column.fieldname === "amount") {
			if (data && data.amount == null) return "";
			var formatted = default_formatter(value, row, column, data);
			if (data && data.is_group) formatted = "<b>" + formatted + "</b>";
			return formatted;
		}

		return default_formatter(value, row, column, data);
	},

	onload: function (report) {
		// Fiscal Year → auto-fill period dates
		var fy_field = report.page.fields_dict && report.page.fields_dict["fiscal_year"];
		if (fy_field) {
			fy_field.df.onchange = function () {
				var fy = report.get_filter_value("fiscal_year");
				if (!fy) return;
				frappe.db.get_doc("Fiscal Year", fy).then(function (doc) {
					report.set_filter_value("period_start_date", doc.year_start_date);
					report.set_filter_value("period_end_date", doc.year_end_date);
				});
			};
		}

		// Set default fiscal year on load
		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Fiscal Year",
				filters: { disabled: 0 },
				fields: ["name", "year_start_date", "year_end_date"],
				order_by: "year_start_date desc",
				limit: 1,
			},
			callback: function (r) {
				if (r.message && r.message.length) {
					var fy = r.message[0];
					report.set_filter_value("fiscal_year", fy.name);
					report.set_filter_value("period_start_date", fy.year_start_date);
					report.set_filter_value("period_end_date", fy.year_end_date);
				}
			},
		});

		// Guide button
		report.page.add_inner_button(__("Configuration Guide"), function () {
			frappe.set_route("cash-flow-guide");
		});

		// Drill-down — always navigate to General Ledger query report
		$(report.wrapper).on("click", ".cf-drill", function (e) {
			e.preventDefault();
			var $el = $(this);
			var f = report.get_filter_values();
			var fd = f.period_start_date || f.from_date || frappe.datetime.year_start();
			var td = f.period_end_date   || f.to_date   || frappe.datetime.get_today();

			// Net Profit row → Gross & Net Profit report
			if ($el.data("link-type") === "profit_loss") {
				frappe.set_route("query-report", "Periodic Gross and Net Profit", {
					company: f.company,
					from_date: fd,
					to_date: td,
				});
				return;
			}

			// Build GL route options
			var gl_opts = {
				company: f.company,
				from_date: fd,
				to_date: td,
				group_by: "Group by Voucher",
			};

			// Attach account(s) if configured — GL account filter is MultiSelectList
			var enc = $el.attr("data-enc");
			if (enc) {
				try {
					var accounts = JSON.parse(decodeURIComponent(enc));
					if (accounts && accounts.length) {
						// MultiSelectList accepts an array; single account also works as array
						gl_opts.account = accounts;
					}
				} catch (_e) { /* navigate without account filter */ }
			}

			frappe.set_route("query-report", "General Ledger", gl_opts);
		});
	},
};
