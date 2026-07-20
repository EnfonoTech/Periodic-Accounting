"""
Reconciliation Stock Entries
────────────────────────────
Drill-down for the Realtime Trading Account Report's 'Reconciliation to Trial
Balance' line — the stock movements that are NEITHER purchases (Purchase Receipt /
Purchase Invoice / Landed Cost Voucher) NOR sales booked to COGS (Sales Invoice /
Delivery Note posted to a Cost-of-Goods-Sold account).

Two movement types:
  Stock Entries — Stock Entry, Stock Reconciliation, etc. (opening-load, write-offs,
                  adjustments).
  Transfers     — Delivery Note / Sales Invoice stock legs that did NOT hit a COGS
                  account (inter-warehouse transfers routed via an in-transit warehouse).

Summing 'Value Change' here equals the report's reconciliation figure MINUS the
per-voucher Stock-Ledger ↔ GL valuation drift (which is not a discrete movement and
is shown as its own line in the trading report).
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
        {"label": _("Voucher Type"), "fieldname": "voucher_type",           "fieldtype": "Data",         "width": 160},
        {"label": _("Voucher No"),   "fieldname": "voucher_no",             "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 180},
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
    co = filters.get("company")
    fd = str(filters.from_date)
    td = str(filters.to_date)

    cogs_sub = (
        "SELECT gle.voucher_no FROM `tabGL Entry` gle "
        "INNER JOIN `tabAccount` acc ON acc.name = gle.account "
        "WHERE gle.company = %s AND gle.posting_date BETWEEN %s AND %s "
        "AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND gle.is_cancelled = 0 "
        "AND acc.root_type = 'Expense' AND acc.account_type = 'Cost of Goods Sold'"
    )
    stock_clause = ("sle.voucher_type NOT IN "
                    "('Purchase Receipt','Purchase Invoice','Landed Cost Voucher','Delivery Note','Sales Invoice')")
    transfer_clause = ("(sle.voucher_type IN ('Delivery Note','Sales Invoice') "
                       "AND sle.voucher_no NOT IN (" + cogs_sub + "))")

    mt = filters.get("movement_type")
    if mt == "Stock Entries":
        type_clause, type_params = stock_clause, []
    elif mt == "Transfers":
        type_clause, type_params = transfer_clause, [co, fd, td]
    else:
        type_clause, type_params = "(" + stock_clause + " OR " + transfer_clause + ")", [co, fd, td]

    query = (
        "SELECT sle.posting_date, sle.voucher_type, sle.voucher_no, sle.item_code, itm.item_name, sle.warehouse, "
        "  CASE WHEN sle.actual_qty > 0 THEN  sle.actual_qty ELSE 0 END AS qty_in, "
        "  CASE WHEN sle.actual_qty < 0 THEN -sle.actual_qty ELSE 0 END AS qty_out, "
        "  sle.valuation_rate, sle.stock_value_difference "
        "FROM `tabStock Ledger Entry` sle LEFT JOIN `tabItem` itm ON itm.name = sle.item_code " + join + " "
        "WHERE " + wh_clause + " AND sle.posting_date BETWEEN %s AND %s AND sle.is_cancelled = 0 "
        "AND " + type_clause + " "
        "ORDER BY sle.voucher_type, sle.posting_date, sle.voucher_no, sle.item_code"
    )
    raw = frappe.db.sql(query, wh_params + [fd, td] + type_params, as_dict=True)

    from collections import defaultdict
    groups = defaultdict(list)
    for r in raw:
        groups[r.voucher_type].append(r)

    result = []
    grand_in = grand_out = grand_val = grand_cnt = 0
    for vtype in sorted(groups):
        grp = groups[vtype]
        result.extend(grp)
        sub_in  = sum(flt(r.qty_in)  for r in grp)
        sub_out = sum(flt(r.qty_out) for r in grp)
        sub_val = sum(flt(r.stock_value_difference) for r in grp)
        cnt     = len(grp)
        result.append({
            "posting_date": None, "voucher_no": None, "item_code": None,
            "item_name": None, "warehouse": None,
            "voucher_type": vtype + "  —  Subtotal (" + str(cnt) + (" line" if cnt == 1 else " lines") + ")",
            "qty_in": sub_in, "qty_out": sub_out, "valuation_rate": None,
            "stock_value_difference": sub_val, "_row_type": "subtotal",
        })
        result.append({})
        grand_in += sub_in; grand_out += sub_out; grand_val += sub_val; grand_cnt += cnt

    if grand_cnt:
        result.append({
            "posting_date": None, "voucher_no": None, "item_code": None,
            "item_name": None, "warehouse": None,
            "voucher_type": "Grand Total  —  " + str(grand_cnt) + (" entry" if grand_cnt == 1 else " entries"),
            "qty_in": grand_in, "qty_out": grand_out, "valuation_rate": None,
            "stock_value_difference": grand_val, "_row_type": "total",
        })
    return result
