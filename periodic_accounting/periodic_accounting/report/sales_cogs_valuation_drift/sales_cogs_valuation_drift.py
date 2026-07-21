"""
Sales COGS Valuation Drift
──────────────────────────
Drill for the Realtime Trading Account Report line
    'Valuation & GL Differences → Sales valuation drift'.

For every Sales Invoice / Delivery Note that posted to a Cost-of-Goods-Sold account,
compares the COGS amount booked in the GL against the stock value that actually left
per the Stock Ledger:

        Drift = GL COGS Posted − Stock Value Out

Vouchers whose drift is material (|drift| >= THRESHOLD) are listed individually; the
remaining tiny per-voucher moving-average rounding drifts are folded into a single
'Other vouchers — rounding drift' line so the grand total ties EXACTLY to the
'Sales valuation drift' figure in the trading report.
"""
import frappe
from frappe import _
from frappe.utils import flt
from periodic_accounting.periodic_accounting.report.report_utils import sle_warehouse_clause

THRESHOLD = 1.0   # BHD — list vouchers with drift at least this; bucket the rest


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    co = filters.get("company"); fd = filters.get("from_date"); td = filters.get("to_date")
    if not (co and fd and td):
        return columns, []
    return columns, get_data(filters)


def get_columns():
    return [
        {"label": _("Voucher Type"),       "fieldname": "voucher_type",    "fieldtype": "Data",         "width": 150},
        {"label": _("Voucher No"),         "fieldname": "voucher_no",      "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 200},
        {"label": _("Date"),               "fieldname": "posting_date",    "fieldtype": "Date",         "width": 100},
        {"label": _("GL COGS Posted"),     "fieldname": "gl_cogs",         "fieldtype": "Currency",     "width": 150},
        {"label": _("Stock Value Out"),    "fieldname": "stock_value_out", "fieldtype": "Currency",     "width": 150},
        {"label": _("Drift (GL − Stock)"), "fieldname": "drift",           "fieldtype": "Currency",     "width": 150},
    ]


def get_data(filters):
    co = filters.get("company"); fd = str(filters.from_date); td = str(filters.to_date)
    cc = filters.get("cost_center")
    cc_clause = " AND gle.cost_center=%s" if cc else ""
    cc_param = [cc] if cc else []

    gl_rows = frappe.db.sql(
        "SELECT gle.voucher_no, gle.voucher_type, MIN(gle.posting_date) AS posting_date, "
        "       COALESCE(SUM(gle.debit-gle.credit),0) AS gl_cogs "
        "FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account "
        "WHERE gle.company=%s AND gle.posting_date BETWEEN %s AND %s AND gle.is_cancelled=0 "
        "AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold' "
        "AND gle.voucher_type IN ('Sales Invoice','Delivery Note') " + cc_clause + " "
        "GROUP BY gle.voucher_no, gle.voucher_type",
        [co, fd, td] + cc_param, as_dict=True)
    if not gl_rows:
        return []
    vnos = [r.voucher_no for r in gl_rows]

    join, wh_clause, wh_params = sle_warehouse_clause(filters)
    ph = ",".join(["%s"] * len(vnos))
    sle_rows = frappe.db.sql(
        "SELECT sle.voucher_no, COALESCE(SUM(sle.stock_value_difference),0) AS svd "
        "FROM `tabStock Ledger Entry` sle " + join + " "
        "WHERE " + wh_clause + " AND sle.posting_date BETWEEN %s AND %s AND sle.is_cancelled=0 "
        "AND sle.voucher_type IN ('Sales Invoice','Delivery Note') "
        "AND sle.voucher_no IN (" + ph + ") "
        "GROUP BY sle.voucher_no",
        wh_params + [fd, td] + vnos, as_dict=True)
    svd_map = {r.voucher_no: flt(r.svd) for r in sle_rows}

    details = []
    tot_gl = tot_out = tot_drift = 0.0          # aggregate totals over ALL vouchers
    shown_gl = shown_out = shown_drift = 0.0
    small_cnt = 0
    for r in gl_rows:
        gl_cogs   = flt(r.gl_cogs)
        stock_out = -flt(svd_map.get(r.voucher_no, 0.0))     # svd < 0 for stock leaving
        drift     = gl_cogs - stock_out
        tot_gl += gl_cogs; tot_out += stock_out; tot_drift += drift
        if abs(flt(drift, 3)) >= THRESHOLD:
            details.append({
                "voucher_type": r.voucher_type, "voucher_no": r.voucher_no,
                "posting_date": r.posting_date, "gl_cogs": flt(gl_cogs, 3),
                "stock_value_out": flt(stock_out, 3), "drift": flt(drift, 3),
            })
            shown_gl += gl_cogs; shown_out += stock_out; shown_drift += drift
        else:
            small_cnt += 1

    details.sort(key=lambda x: -abs(x["drift"]))

    # rounding-residual bucket so the total ties exactly to the trading report
    res_drift = flt(tot_drift - shown_drift, 3)
    if small_cnt and abs(res_drift) >= 0.0005:
        details.append({
            "voucher_type": "Other vouchers — rounding drift  (" + str(small_cnt) +
                            (" voucher" if small_cnt == 1 else " vouchers") + ", each < " + str(THRESHOLD) + ")",
            "gl_cogs": flt(tot_gl - shown_gl, 3), "stock_value_out": flt(tot_out - shown_out, 3),
            "drift": res_drift, "_row_type": "subtotal",
        })

    if details:
        details.append({
            "voucher_type": "Grand Total  —  Sales Valuation Drift",
            "gl_cogs": flt(tot_gl, 3), "stock_value_out": flt(tot_out, 3), "drift": flt(tot_drift, 3),
            "_row_type": "total",
        })
    return details
