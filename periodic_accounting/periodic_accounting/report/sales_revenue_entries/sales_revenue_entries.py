"""
Sales Revenue Entries
─────────────────────
Drill-down for the Realtime Trading Account Report's SALES head — the GL income
postings behind Gross Sales / Returns / Net Sales.

Source: GL Entries on Income accounts (root_type='Income') from Sales Invoice and
Delivery Note.  Credit = revenue, Debit = returns / credit notes; net (Credit −
Debit) = Net Sales.  Grouped by voucher type with subtotals and a grand total.
"""
import frappe
from frappe import _
from frappe.utils import flt


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
        {"label": _("Date"),           "fieldname": "posting_date",  "fieldtype": "Date",         "width": 100},
        {"label": _("Voucher Type"),   "fieldname": "voucher_type",  "fieldtype": "Data",         "width": 140},
        {"label": _("Voucher No"),     "fieldname": "voucher_no",    "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 180},
        {"label": _("Customer"),       "fieldname": "party",         "fieldtype": "Data",         "width": 200},
        {"label": _("Income Account"), "fieldname": "account",       "fieldtype": "Link",         "options": "Account", "width": 240},
        {"label": _("Returns (Dr)"),   "fieldname": "debit",         "fieldtype": "Currency",     "width": 130},
        {"label": _("Revenue (Cr)"),   "fieldname": "credit",        "fieldtype": "Currency",     "width": 130},
    ]


def get_data(filters):
    co = filters.get("company")
    fd = str(filters.from_date)
    td = str(filters.to_date)

    conds = ""
    params = [co, fd, td]
    if filters.get("cost_center"):
        conds += " AND gle.cost_center = %s"
        params.append(filters.get("cost_center"))
    stype = filters.get("sales_type")
    if stype == "Sales":
        conds += " AND gle.credit > 0"
    elif stype == "Returns":
        conds += " AND gle.debit > 0"

    query = (
        "SELECT gle.posting_date, gle.voucher_type, gle.voucher_no, "
        "  COALESCE(gle.party, '') AS party, gle.account, gle.debit, gle.credit "
        "FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name = gle.account "
        "WHERE gle.company = %s AND gle.posting_date BETWEEN %s AND %s AND gle.is_cancelled = 0 "
        "AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND acc.root_type = 'Income'"
        + conds +
        " ORDER BY gle.voucher_type, gle.posting_date, gle.voucher_no"
    )
    raw = frappe.db.sql(query, params, as_dict=True)

    from collections import defaultdict
    groups = defaultdict(list)
    for r in raw:
        groups[r.voucher_type].append(r)

    result = []
    grand_dr = grand_cr = grand_cnt = 0
    for vtype in sorted(groups):
        grp = groups[vtype]
        result.extend(grp)
        sub_dr = sum(flt(r.debit)  for r in grp)
        sub_cr = sum(flt(r.credit) for r in grp)
        cnt    = len(grp)
        result.append({
            "posting_date": None, "voucher_no": None, "party": None, "account": None,
            "voucher_type": vtype + "  —  Subtotal (" + str(cnt) + (" line" if cnt == 1 else " lines") + ")",
            "debit": sub_dr, "credit": sub_cr, "_row_type": "subtotal",
        })
        result.append({})
        grand_dr += sub_dr; grand_cr += sub_cr; grand_cnt += cnt

    if grand_cnt:
        result.append({
            "posting_date": None, "voucher_no": None, "party": None, "account": None,
            "voucher_type": "Grand Total  —  Net Sales " + "{:,.3f}".format(grand_cr - grand_dr),
            "debit": grand_dr, "credit": grand_cr, "_row_type": "total",
        })
    return result
