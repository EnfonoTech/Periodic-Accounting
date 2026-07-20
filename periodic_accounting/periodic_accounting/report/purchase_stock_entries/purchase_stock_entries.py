"""
Purchase Stock Entries
──────────────────────
Drill-down report showing Stock Ledger Entries from Purchase Invoice,
Purchase Receipt, and Landed Cost Voucher only — filtered by date range
and optional warehouse/cost centre.

Used as the drill-down target for 'Gross Purchases' and 'Purchase Returns'
in the Realtime Trading Account and Periodic Gross & Net Profit reports.
"""
import frappe
from frappe import _
from frappe.utils import flt

from periodic_accounting.periodic_accounting.report.report_utils import (
    sle_warehouse_clause,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    co = filters.get("company")
    fd = filters.get("from_date")
    td = filters.get("to_date")
    if not (co and fd and td):
        return columns, []
    return columns, get_data(filters)


def get_columns():
    return [
        {"label": _("Date"),         "fieldname": "posting_date",          "fieldtype": "Date",         "width": 100},
        {"label": _("Voucher Type"), "fieldname": "voucher_type",           "fieldtype": "Data",         "width": 150},
        {"label": _("Voucher No"),   "fieldname": "voucher_no",             "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 180},
        {"label": _("Currency"),     "fieldname": "voucher_currency",       "fieldtype": "Data",         "width": 85},
        {"label": _("Item Code"),    "fieldname": "item_code",              "fieldtype": "Link",         "options": "Item", "width": 130},
        {"label": _("Item Name"),    "fieldname": "item_name",              "fieldtype": "Data",         "width": 200},
        {"label": _("Warehouse"),    "fieldname": "warehouse",              "fieldtype": "Link",         "options": "Warehouse", "width": 160},
        {"label": _("Qty In"),       "fieldname": "qty_in",                 "fieldtype": "Float",        "width": 80},
        {"label": _("Qty Out"),      "fieldname": "qty_out",                "fieldtype": "Float",        "width": 80},
        {"label": _("Rate"),         "fieldname": "valuation_rate",         "fieldtype": "Currency",     "width": 110},
        {"label": _("Value Change"), "fieldname": "stock_value_difference", "fieldtype": "Currency",     "width": 130},
    ]


def get_data(filters):
    join, wh_clause, wh_params = sle_warehouse_clause(filters)

    co_currency = frappe.db.get_value(
        "Company", filters.get("company"), "default_currency") or ""

    # Local vs Import: voucher currency vs company currency, PLUS migrated ePromise
    # imports (epromise_vr 'IP…') which post in company currency but are imports.
    ip_parts = []
    if frappe.db.has_column("Purchase Invoice", "epromise_vr"):
        ip_parts.append("pi.epromise_vr LIKE 'IP%%'")
    if frappe.db.has_column("Purchase Receipt", "epromise_vr"):
        ip_parts.append("pr.epromise_vr LIKE 'IP%%'")
    ip_or      = (" OR " + " OR ".join(ip_parts)) if ip_parts else ""
    ip_and_not = (" AND NOT (" + " OR ".join(ip_parts) + ")") if ip_parts else ""

    ptype_clause, ptype_params = "", []
    ptype = filters.get("purchase_type")
    if ptype == "Local":
        ptype_clause = (" AND sle.voucher_type != 'Landed Cost Voucher'"
                        " AND COALESCE(pr.currency, pi.currency, %s) = %s" + ip_and_not +
                        " AND sle.stock_value_difference >= 0")
        ptype_params = [co_currency, co_currency]
    elif ptype == "Import":
        ptype_clause = (" AND sle.voucher_type != 'Landed Cost Voucher'"
                        " AND (COALESCE(pr.currency, pi.currency, %s) != %s" + ip_or + ")"
                        " AND sle.stock_value_difference >= 0")
        ptype_params = [co_currency, co_currency]
    elif ptype == "Landed Cost":
        ptype_clause = " AND sle.voucher_type = 'Landed Cost Voucher'"
    elif ptype == "Returns":
        ptype_clause = (" AND sle.voucher_type != 'Landed Cost Voucher'"
                        " AND sle.stock_value_difference < 0")

    raw = frappe.db.sql(
        f"""SELECT
                sle.posting_date,
                sle.voucher_type,
                sle.voucher_no,
                COALESCE(pr.currency, pi.currency, %s) AS voucher_currency,
                sle.item_code,
                itm.item_name,
                sle.warehouse,
                CASE WHEN sle.actual_qty > 0 THEN  sle.actual_qty ELSE 0 END AS qty_in,
                CASE WHEN sle.actual_qty < 0 THEN -sle.actual_qty ELSE 0 END AS qty_out,
                sle.valuation_rate,
                sle.stock_value_difference
            FROM `tabStock Ledger Entry` sle
            LEFT JOIN `tabItem` itm ON itm.name = sle.item_code
            LEFT JOIN `tabPurchase Receipt` pr
                ON pr.name = sle.voucher_no AND sle.voucher_type = 'Purchase Receipt'
            LEFT JOIN `tabPurchase Invoice` pi
                ON pi.name = sle.voucher_no AND sle.voucher_type = 'Purchase Invoice'
            {join}
            WHERE {wh_clause}
              AND sle.posting_date BETWEEN %s AND %s
              AND sle.voucher_type IN (
                  'Purchase Invoice', 'Purchase Receipt', 'Landed Cost Voucher'
              )
              AND sle.is_cancelled = 0
              {ptype_clause}
            ORDER BY sle.voucher_type, sle.posting_date, sle.voucher_no, sle.item_code""",
        [co_currency] + wh_params
        + [str(filters.from_date), str(filters.to_date)] + ptype_params,
        as_dict=True,
    )

    # Build result with per-group subtotals and a grand total
    VOUCHER_ORDER = ["Purchase Receipt", "Purchase Invoice", "Landed Cost Voucher"]
    from collections import defaultdict
    groups = defaultdict(list)
    for r in raw:
        groups[r.voucher_type].append(r)

    result = []
    grand_in  = grand_out = grand_val = grand_cnt = 0

    for vtype in VOUCHER_ORDER + [v for v in groups if v not in VOUCHER_ORDER]:
        grp = groups.get(vtype, [])
        if not grp:
            continue
        result.extend(grp)
        sub_in  = sum(flt(r.qty_in)  for r in grp)
        sub_out = sum(flt(r.qty_out) for r in grp)
        sub_val = sum(flt(r.stock_value_difference) for r in grp)
        cnt     = len(grp)
        result.append({
            "posting_date": None, "voucher_no": None,
            "item_code": None, "item_name": None, "warehouse": None,
            "voucher_type": f"{vtype}  —  Subtotal ({cnt} line{'s' if cnt != 1 else ''})",
            "qty_in": sub_in, "qty_out": sub_out,
            "valuation_rate": None, "stock_value_difference": sub_val,
            "_row_type": "subtotal",
        })
        result.append({})   # blank row between groups
        grand_in  += sub_in
        grand_out += sub_out
        grand_val += sub_val
        grand_cnt += cnt

    if grand_cnt:
        result.append({
            "posting_date": None, "voucher_no": None,
            "item_code": None, "item_name": None, "warehouse": None,
            "voucher_type": f"Grand Total  —  {grand_cnt} entr{'ies' if grand_cnt != 1 else 'y'}",
            "qty_in": grand_in, "qty_out": grand_out,
            "valuation_rate": None, "stock_value_difference": grand_val,
            "_row_type": "total",
        })

    return result
