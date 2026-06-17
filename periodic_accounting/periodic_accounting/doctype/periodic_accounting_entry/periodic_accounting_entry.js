frappe.ui.form.on("Periodic Accounting Entry", {

	refresh(frm) {
		frm.trigger("set_account_filters");
		frm.clear_custom_buttons();

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Balance"), () => {
				frm.trigger("get_balance");
			}).addClass("btn-primary");
		}

		if (frm.doc.journal_entry) {
			frm.add_custom_button(
				__("View Journal Entry"),
				() => frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry),
				__("Links")
			);
		}
	},

	set_account_filters(frm) {
		frm.set_query("stock_account", () => ({
			filters: {
				company: frm.doc.company,
				account_type: "Stock",
				root_type: "Asset",
				is_group: 0,
			}
		}));

		frm.set_query("difference_account", () => ({
			filters: {
				company: frm.doc.company,
				account_type: "Cost of Goods Sold",
				root_type: "Expense",
				is_group: 0,
			}
		}));

		frm.set_query("company", () => ({
			filters: { enable_perpetual_inventory: 0 }
		}));

		frm.set_query("cost_center", () => ({
			filters: { company: frm.doc.company, is_group: 0 }
		}));
	},

	get_balance(frm) {
		if (!frm.doc.company) {
			frappe.msgprint(__("Please select a Company first."));
			return;
		}
		if (!frm.doc.posting_date) {
			frappe.msgprint(__("Please set a Posting Date first."));
			return;
		}
		if (!frm.doc.difference_account) {
			frappe.msgprint(__("Please select a Difference Account (COGS)."));
			return;
		}

		frm.call({
			method: "get_balance",
			doc: frm.doc,
			callback(r) {
				frm.refresh_field("accounts");
				frm.refresh_field("remarks");
			}
		});
	},

	for_all_stock_accounts(frm) {
		frm.toggle_reqd("stock_account", !frm.doc.for_all_stock_accounts);
		frm.toggle_display("stock_account", !frm.doc.for_all_stock_accounts);
	},

	company(frm) {
		frm.set_value("accounts", []);
		frm.set_value("difference_account", "");
		frm.set_value("cost_center", "");
	},

	posting_date(frm) {
		frm.set_value("accounts", []);
	},
});
