"""
COGS Non-Sales Postings
───────────────────────
Drill for the Realtime Trading Account Report line
    'Valuation & GL Differences → Non-sales COGS postings'.

Every GL posting to a Cost-of-Goods-Sold account whose voucher is NOT a sale
(Sales Invoice / Delivery Note) — e.g. a Purchase Receipt valuation leg, a Journal
Entry, or a stock adjustment booked straight to COGS. The Net (Dr − Cr) grand total
equals the 'Non-sales COGS postings' figure in the trading report.
"""
import frappe
from frappe import _
from frappe.utils import flt
from collections import defaultdict


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    co = filters.get("company"); fd = filters.get("from_date"); td = filters.get("to_date")
    if not (co and fd and td):
        return columns, []
    return columns, get_data(filters)


def get_columns():
    return [
        {"label": _("Date"),          "fieldname": "posting_date", "fieldtype": "Date",         "width": 100},
        {"label": _("Voucher Type"),  "fieldname": "voucher_type", "fieldtype": "Data",         "width": 150},
        {"label": _("Voucher No"),    "fieldname": "voucher_no",   "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 190},
        {"label": _("COGS Account"),  "fieldname": "account",      "fieldtype": "Link",         "options": "Account", "width": 240},
        {"label": _("Debit"),         "fieldname": "debit",        "fieldtype": "Currency",     "width": 130},
        {"label": _("Credit"),        "fieldname": "credit",       "fieldtype": "Currency",     "width": 130},
        {"label": _("Net (Dr − Cr)"), "fieldname": "net",          "fieldtype": "Currency",     "width": 140},
    ]


def get_data(filters):
    co = filters.get("company"); fd = str(filters.from_date); td = str(filters.to_date)
    cc = filters.get("cost_center")
    cc_clause = " AND gle.cost_center=%s" if cc else ""
    cc_param = [cc] if cc else []
    so = filters.get("stock_only")
    sle_clause = ""; sle_param = []
    if so in (1, "1", 0, "0"):
        op = "IN" if str(so) == "1" else "NOT IN"
        sle_clause = (" AND gle.voucher_no " + op + " (SELECT DISTINCT sle.voucher_no "
                      "FROM `tabStock Ledger Entry` sle WHERE sle.company=%s "
                      "AND sle.posting_date BETWEEN %s AND %s AND sle.is_cancelled=0) ")
        sle_param = [co, fd, td]
    rows = frappe.db.sql(
        "SELECT gle.posting_date, gle.voucher_type, gle.voucher_no, gle.account, "
        "       gle.debit, gle.credit, (gle.debit-gle.credit) AS net "
        "FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account "
        "WHERE gle.company=%s AND gle.posting_date BETWEEN %s AND %s AND gle.is_cancelled=0 "
        "AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold' "
        "AND gle.voucher_type NOT IN ('Sales Invoice','Delivery Note') " + cc_clause + sle_clause + " "
        "ORDER BY gle.voucher_type, gle.posting_date, gle.voucher_no",
        [co, fd, td] + cc_param + sle_param, as_dict=True)

    groups = defaultdict(list)
    for r in rows:
        groups[r.voucher_type].append(r)

    result = []
    g_deb = g_cr = g_net = g_cnt = 0
    for vt in sorted(groups):
        grp = groups[vt]; result.extend(grp)
        s_deb = sum(flt(r.debit) for r in grp)
        s_cr  = sum(flt(r.credit) for r in grp)
        s_net = sum(flt(r.net) for r in grp)
        result.append({
            "voucher_type": vt + "  —  Subtotal (" + str(len(grp)) + (" line" if len(grp) == 1 else " lines") + ")",
            "debit": s_deb, "credit": s_cr, "net": s_net, "_row_type": "subtotal",
        })
        result.append({})
        g_deb += s_deb; g_cr += s_cr; g_net += s_net; g_cnt += len(grp)

    if g_cnt:
        result.append({
            "voucher_type": "Grand Total  —  " + str(g_cnt) + (" entry" if g_cnt == 1 else " entries"),
            "debit": g_deb, "credit": g_cr, "net": g_net, "_row_type": "total",
        })
    return result
