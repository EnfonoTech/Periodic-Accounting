"""
Purchase Invoice Stocked Items
──────────────────────────────
Drill-down report showing Purchase Invoice line items for stocked items only
(is_stock_item=1), using base_net_amount (VAT excluded).

Cross-verification companion for the Audit Trading Account Report.
The Grand Total here must match the Local / Import / Returns figures in that report.

Each row carries a 'Type' column that shows exactly which formula bucket the
value feeds into — Local Purchase, Import Purchase, Local Return, Import Return —
and whether the PI had Update Stock checked (SLE created) or not.

Filters
-------
company      : mandatory
from_date    : mandatory
to_date      : mandatory
warehouse    : optional — filters pii.warehouse
transaction  : All | Purchases | Returns  (default: All)
currency_type: All | Local | Import       (default: All)
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
        {"label": _("Date"),            "fieldname": "posting_date",    "fieldtype": "Date",     "width": 100},
        {"label": _("Purchase Invoice"),"fieldname": "purchase_invoice","fieldtype": "Link",     "options": "Purchase Invoice", "width": 165},
        {"label": _("Supplier"),        "fieldname": "supplier",        "fieldtype": "Link",     "options": "Supplier", "width": 175},
        {"label": _("Type"),            "fieldname": "txn_type",        "fieldtype": "Data",     "width": 190},
        {"label": _("Item Code"),       "fieldname": "item_code",       "fieldtype": "Link",     "options": "Item", "width": 130},
        {"label": _("Item Name"),       "fieldname": "item_name",       "fieldtype": "Data",     "width": 200},
        {"label": _("Item Group"),      "fieldname": "item_group",      "fieldtype": "Link",     "options": "Item Group", "width": 120},
        {"label": _("Qty"),             "fieldname": "qty",             "fieldtype": "Float",    "width": 80},
        {"label": _("UOM"),             "fieldname": "uom",             "fieldtype": "Data",     "width": 60},
        {"label": _("Rate (Base)"),     "fieldname": "base_rate",       "fieldtype": "Currency", "width": 120},
        {"label": _("Net Amt (Base)"),  "fieldname": "base_net_amount", "fieldtype": "Currency", "width": 145},
        {"label": _("Warehouse"),       "fieldname": "warehouse",       "fieldtype": "Link",     "options": "Warehouse", "width": 155},
    ]


def _txn_type(company_cur, currency, is_return, update_stock):
    """Return a human-readable label for the formula bucket this line feeds."""
    cur       = currency or company_cur
    direction = "Return" if is_return else "Purchase"
    locality  = "Local" if cur == company_cur else "Import"
    upd       = "" if update_stock else "  (no stock update)"
    return f"{locality} {direction}{upd}"


def get_data(filters):
    co    = filters.get("company")
    fd    = str(filters.get("from_date"))
    td    = str(filters.get("to_date"))
    wh    = filters.get("warehouse")
    txn   = filters.get("transaction") or "All"
    ctype = filters.get("currency_type") or "All"

    company_cur = frappe.db.get_value("Company", co, "default_currency") or ""

    # ── WHERE clauses ─────────────────────────────────────────────────────────
    conditions = [
        "pi.company = %s",
        "pi.posting_date BETWEEN %s AND %s",
        "pi.docstatus = 1",
        "itm.is_stock_item = 1",
    ]
    params = [co, fd, td]

    if wh:
        conditions.append("pii.warehouse = %s")
        params.append(wh)

    if txn == "Purchases":
        conditions.append("pi.is_return = 0")
    elif txn == "Returns":
        conditions.append("pi.is_return = 1")

    if ctype == "Local":
        conditions.append("COALESCE(pi.currency, %s) = %s")
        params += [company_cur, company_cur]
    elif ctype == "Import":
        conditions.append("COALESCE(pi.currency, %s) != %s")
        params += [company_cur, company_cur]

    where = " AND ".join(conditions)

    raw = frappe.db.sql(f"""
        SELECT
            pi.posting_date,
            pi.name         AS purchase_invoice,
            pi.supplier,
            pi.currency,
            pi.update_stock,
            pi.is_return,
            pii.item_code,
            itm.item_name,
            itm.item_group,
            pii.qty,
            pii.uom,
            pii.base_rate,
            pii.base_net_amount,
            pii.warehouse
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi  ON pi.name = pii.parent
        INNER JOIN `tabItem`             itm ON itm.name = pii.item_code
        WHERE {where}
        ORDER BY pi.posting_date, pi.name, pii.idx
    """, params, as_dict=True)

    if not raw:
        return []

    # ── Attach type label to each row ─────────────────────────────────────────
    for r in raw:
        r["txn_type"] = _txn_type(company_cur, r.currency, r.is_return, r.update_stock)

    # ── Group by PI with subtotals ────────────────────────────────────────────
    result      = []
    grand_total = 0.0
    grand_qty   = 0.0
    grand_cnt   = 0

    from itertools import groupby
    for pi_name, lines in groupby(raw, key=lambda r: r.purchase_invoice):
        lines = list(lines)
        result.extend(lines)

        sub_net = sum(flt(r.base_net_amount) for r in lines)
        sub_qty = sum(flt(r.qty) for r in lines)
        n       = len(lines)
        first   = lines[0]
        lbl     = f"{pi_name}  —  {first.supplier}  ({n} item{'s' if n != 1 else ''})"

        result.append({
            "posting_date":    None,
            "purchase_invoice": lbl,
            "supplier":         None,
            "txn_type":         first.txn_type,
            "item_code":        None,
            "item_name":        None,
            "item_group":       None,
            "qty":              sub_qty,
            "uom":              None,
            "base_rate":        None,
            "base_net_amount":  sub_net,
            "warehouse":        None,
            "_row_type":        "subtotal",
        })
        result.append({})   # blank spacer between PIs

        grand_total += sub_net
        grand_qty   += sub_qty
        grand_cnt   += n

    # ── Grand total ───────────────────────────────────────────────────────────
    if grand_cnt:
        result.append({
            "posting_date":    None,
            "purchase_invoice": f"Grand Total  —  {grand_cnt} line{'s' if grand_cnt != 1 else ''}",
            "supplier":         None,
            "txn_type":         None,
            "item_code":        None,
            "item_name":        None,
            "item_group":       None,
            "qty":              grand_qty,
            "uom":              None,
            "base_rate":        None,
            "base_net_amount":  grand_total,
            "warehouse":        None,
            "_row_type":        "total",
        })

    return result
