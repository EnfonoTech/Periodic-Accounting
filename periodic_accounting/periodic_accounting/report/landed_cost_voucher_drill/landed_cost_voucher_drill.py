"""
Landed Cost Voucher Drill
─────────────────────────
Drill-down report showing submitted Landed Cost Vouchers and their charges.
Grand total of the Amount column matches the 'Landed Cost Vouchers' line
in the Audit Trading Account Report.

Each LCV is grouped with its source receipts (for context) and its
tax/charge rows (the actual amounts that flow into the report formula).
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    co = filters.get("company")
    fd = filters.get("from_date")
    td = filters.get("to_date")
    if not (co and fd and td):
        return get_columns(), []
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"label": _("Date"),            "fieldname": "posting_date",   "fieldtype": "Date",    "width": 100},
        {"label": _("LCV"),             "fieldname": "lcv_name",       "fieldtype": "Link",    "options": "Landed Cost Voucher", "width": 170},
        {"label": _("Source Doc Type"), "fieldname": "src_type",       "fieldtype": "Data",    "width": 130},
        {"label": _("Source Document"), "fieldname": "src_doc",        "fieldtype": "Dynamic Link", "options": "src_type", "width": 180},
        {"label": _("Supplier"),        "fieldname": "supplier",       "fieldtype": "Link",    "options": "Supplier", "width": 160},
        {"label": _("Charge Account"),  "fieldname": "expense_account","fieldtype": "Link",    "options": "Account", "width": 220},
        {"label": _("Description"),     "fieldname": "description",    "fieldtype": "Data",    "width": 180},
        {"label": _("Amount"),          "fieldname": "amount",         "fieldtype": "Currency","width": 130},
    ]


def get_data(filters):
    co = filters.get("company")
    fd = str(filters.get("from_date"))
    td = str(filters.get("to_date"))
    wh = filters.get("warehouse")

    wh_clause = ""
    wh_params = []
    if wh:
        wh_clause = """
            AND EXISTS (
                SELECT 1 FROM `tabLanded Cost Item` lci2
                WHERE lci2.parent = lcv.name AND lci2.warehouse = %s
            )
        """
        wh_params = [wh]

    # Fetch all submitted LCVs in range
    lcvs = frappe.db.sql(f"""
        SELECT lcv.name, lcv.posting_date
        FROM `tabLanded Cost Voucher` lcv
        WHERE lcv.company = %s
          AND lcv.posting_date BETWEEN %s AND %s
          AND lcv.docstatus = 1
          {wh_clause}
        ORDER BY lcv.posting_date, lcv.name
    """, [co, fd, td] + wh_params, as_dict=True)

    if not lcvs:
        return []

    result     = []
    grand_total = 0.0
    grand_cnt  = 0

    for lcv_row in lcvs:
        lcv_name = lcv_row.name

        # Source receipts for this LCV
        sources = frappe.db.sql("""
            SELECT receipt_document_type, receipt_document, supplier
            FROM `tabLanded Cost Purchase Receipt`
            WHERE parent = %s
            ORDER BY idx
        """, lcv_name, as_dict=True)

        # Charge rows for this LCV
        charges = frappe.db.sql("""
            SELECT expense_account, description, amount
            FROM `tabLanded Cost Taxes and Charges`
            WHERE parent = %s
            ORDER BY idx
        """, lcv_name, as_dict=True)

        lcv_total = sum(flt(c.amount) for c in charges)

        # One source row per receipt (for context, amount blank)
        for src in sources:
            result.append({
                "posting_date":    lcv_row.posting_date,
                "lcv_name":        lcv_name,
                "src_type":        src.receipt_document_type,
                "src_doc":         src.receipt_document,
                "supplier":        src.supplier,
                "expense_account": None,
                "description":     None,
                "amount":          None,
                "_row_type":       "source",
            })

        # One charge row per tax line (these feed the report total)
        for ch in charges:
            result.append({
                "posting_date":    lcv_row.posting_date,
                "lcv_name":        lcv_name,
                "src_type":        None,
                "src_doc":         None,
                "supplier":        None,
                "expense_account": ch.expense_account,
                "description":     ch.description,
                "amount":          flt(ch.amount),
                "_row_type":       "charge",
            })

        # LCV subtotal
        result.append({
            "posting_date":    None,
            "lcv_name":        f"{lcv_name}  —  Total",
            "src_type":        None,
            "src_doc":         None,
            "supplier":        None,
            "expense_account": None,
            "description":     None,
            "amount":          lcv_total,
            "_row_type":       "subtotal",
        })
        result.append({})  # blank spacer

        grand_total += lcv_total
        grand_cnt   += 1

    if grand_cnt:
        result.append({
            "posting_date":    None,
            "lcv_name":        f"Grand Total  —  {grand_cnt} LCV{'s' if grand_cnt != 1 else ''}",
            "src_type":        None,
            "src_doc":         None,
            "supplier":        None,
            "expense_account": None,
            "description":     None,
            "amount":          grand_total,
            "_row_type":       "total",
        })

    return result
