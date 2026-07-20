"""
Realtime Trading Account Report — Perpetual Inventory (GL-truthful mirror)
─────────────────────────────────────────────────────────────────────────
Same layout / features as the Audit Trading Account Report, but PURCHASES are
sourced from the documents that actually INCREASE STOCK (Purchase Receipt and
Purchase Invoice with update_stock) valued at the Stock Ledger valuation that
posts to the stock account (stock_value_difference) — not from Purchase Invoice
net amounts.  Because that valuation is exactly what hits the GL, and because

        Closing = Opening + Σ(all period SLE stock_value_difference)

the trading formula

        NET COGS = Opening + Purchases + Adjustments − Closing

telescopes to the stock consumed by sales, i.e. it equals the GL / Trial-Balance
Cost of Goods Sold.  A verification row proves the tie-out on screen.

  * Purchases   — SLE for voucher_type in (Purchase Receipt, Purchase Invoice,
                  Landed Cost Voucher).  Local vs Import by the source document's
                  currency vs the company currency (LCV shown separately).
  * Adjustments — SLE for every OTHER voucher type (Stock Entry, Stock
                  Reconciliation, …) so the formula ties out exactly.
  * COGS side   — Sales / GL COGS identical to the Audit report.
"""
import json

import frappe
from frappe import _
from frappe.utils import flt, getdate, today, add_days
from urllib.parse import urlencode


PURCHASE_VTYPES = ("Purchase Receipt", "Purchase Invoice", "Landed Cost Voucher")
SALES_VTYPES    = ("Delivery Note", "Sales Invoice")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()

    co = filters.company
    fd = filters.get("from_date")
    td = filters.get("to_date")

    if not co or not fd or not td:
        return columns, [], None, None, None

    fd = str(fd); td = str(td)
    wh = filters.get("warehouse")
    if wh and frappe.db.get_value("Warehouse", wh, "is_group"):
        wh = None
    cc = filters.get("cost_center")

    rows, kv = build_main(co, fd, td, wh, cc)
    return columns, rows, None, _make_chart(kv), _make_summary(kv)


def get_columns():
    return [
        {"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data",     "width": 380},
        {"label": _("Dr"),          "fieldname": "debit",       "fieldtype": "Currency",  "width": 170},
        {"label": _("Cr"),          "fieldname": "credit",      "fieldtype": "Currency",  "width": 170},
    ]


# ── URL helpers ───────────────────────────────────────────────────────────────

def _url(report, params):
    return "/app/query-report/" + report.replace(" ", "%20") + "?" + urlencode(params)

def _sl(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Stock Ledger", p)

def _sb(co, fd, td, wh=None):
    p = {"company": co, "from_date": str(fd), "to_date": str(td)}
    if wh: p["warehouse"] = wh
    return _url("Stock Balance", p)

def _sr(co, fd, td):
    return _url("Sales Register", {"company": co, "from_date": fd, "to_date": td})

def _pse(co, fd, td, wh=None, ptype=None):
    """Purchase Stock Entries drill — same SLE (PR/PI/LCV) source as this report,
    carrying the Local / Import / Landed Cost / Returns classification."""
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    if ptype: p["purchase_type"] = ptype
    return _url("Purchase Stock Entries", p)

def _sse(co, fd, td, wh=None):
    """Sales Stock Entries drill — outgoing stock from BOTH Sales Invoice and
    Delivery Note (DN sales that ship stock without an invoice are included)."""
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Sales Stock Entries", p)


# ── SLE aggregation ───────────────────────────────────────────────────────────

def _wh_base(company, warehouse):
    if warehouse:
        return "", ["sle.company=%s", "sle.warehouse=%s", "sle.is_cancelled=0"], [company, warehouse]
    return (
        "INNER JOIN `tabWarehouse` w ON w.name=sle.warehouse",
        ["w.company=%s", "w.disabled=0",
         "(w.warehouse_type IS NULL OR w.warehouse_type!='Transit')", "sle.is_cancelled=0"],
        [company],
    )


def _sle(company, warehouse, extra_conds, extra_params, select):
    j, c, p = _wh_base(company, warehouse)
    where = " AND ".join(c + extra_conds)
    query = "SELECT " + select + " FROM `tabStock Ledger Entry` sle " + j + " WHERE " + where
    return frappe.db.sql(query, p + extra_params, as_dict=True)


def opening_stock(co, fd, wh=None):
    """Opening stock = closing stock as of the day before from_date (Tally convention)."""
    return closing_stock(co, str(add_days(fd, -1)), wh)


def closing_stock(co, td, wh=None):
    if getdate(td) >= getdate(today()):
        if wh:
            r = frappe.db.sql(
                "SELECT COALESCE(SUM(stock_value),0) AS v FROM `tabBin` WHERE warehouse=%s",
                wh, as_dict=True)
        else:
            r = frappe.db.sql("""
                SELECT COALESCE(SUM(b.stock_value),0) AS v
                FROM `tabBin` b INNER JOIN `tabWarehouse` w ON w.name=b.warehouse
                WHERE w.company=%s AND w.disabled=0
                  AND (w.warehouse_type IS NULL OR w.warehouse_type!='Transit')
            """, co, as_dict=True)
        return flt(r[0].v) if r else 0.0
    r = _sle(co, wh, ["sle.posting_date<=%s"], [td],
             "COALESCE(SUM(sle.stock_value_difference),0) AS v")
    return flt(r[0].v) if r else 0.0


def purchase_split(co, fd, td, wh=None, cc_vnos=None):
    """
    Purchases from STOCK-INCREASING documents, valued at SLE stock_value_difference.

    Source: Stock Ledger Entries whose voucher is a Purchase Receipt or Purchase
    Invoice (update_stock creates the SLE naturally).
      local_pur  — company currency (and not a migrated IP voucher), value change >= 0
      import_pur — foreign currency OR a migrated import (epromise_vr 'IP…', posted in
                   company currency), value change >= 0
      pur_ret    — value change < 0 (returns), returned as a positive number

    Landed Cost is not a separate line: ERPNext reposts it into the PR/PI valuation, so
    it is already inside local/import (and hence in closing stock).
    Sign-based (value change >= 0 / < 0) mirrors the Purchase Stock Entries drill.
    """
    company_cur = frappe.db.get_value("Company", co, "default_currency") or ""
    j, c, p = _wh_base(co, wh)

    vno = ""
    vp  = []
    if cc_vnos is not None:
        if cc_vnos:
            ph  = ",".join(["%s"] * len(cc_vnos))
            vno = "AND sle.voucher_no IN (" + ph + ")"
            vp  = list(cc_vnos)
        else:
            vno = "AND 1=0"

    # Migrated (ePromise) imports are posted in company currency but tagged epromise_vr
    # 'IP…', so the currency test alone misclassifies them as local. Treat them as import.
    ip_parts = []
    if frappe.db.has_column("Purchase Invoice", "epromise_vr"):
        ip_parts.append("COALESCE(pi.epromise_vr,'') LIKE 'IP%%'")
    if frappe.db.has_column("Purchase Receipt", "epromise_vr"):
        ip_parts.append("COALESCE(pr.epromise_vr,'') LIKE 'IP%%'")
    ip_expr = (" OR " + " OR ".join(ip_parts)) if ip_parts else ""

    where = " AND ".join(c + [
        "sle.posting_date BETWEEN %s AND %s",
        "sle.voucher_type IN ('Purchase Receipt','Purchase Invoice')",
    ])

    query = (
        "SELECT "
        "  CASE WHEN COALESCE(pr.currency, pi.currency, %s) <> %s " + ip_expr + " THEN 1 ELSE 0 END AS is_imp, "
        "  COALESCE(SUM(CASE WHEN sle.stock_value_difference >= 0 "
        "                    THEN sle.stock_value_difference ELSE 0 END), 0) AS pos, "
        "  COALESCE(ABS(SUM(CASE WHEN sle.stock_value_difference < 0 "
        "                    THEN sle.stock_value_difference ELSE 0 END)), 0) AS neg "
        "FROM `tabStock Ledger Entry` sle " + j + " "
        "LEFT JOIN `tabPurchase Receipt`  pr ON sle.voucher_type='Purchase Receipt'  AND pr.name=sle.voucher_no "
        "LEFT JOIN `tabPurchase Invoice`  pi ON sle.voucher_type='Purchase Invoice'  AND pi.name=sle.voucher_no "
        "WHERE " + where + " " + vno + " "
        "GROUP BY is_imp"
    )
    rows = frappe.db.sql(query, [company_cur, company_cur] + p + [fd, td] + vp, as_dict=True)

    local_pur = import_pur = pur_ret = 0.0
    for r in rows:
        if r.is_imp:
            import_pur += flt(r.pos)
        else:
            local_pur  += flt(r.pos)
        pur_ret += flt(r.neg)
    # Landed Cost is embedded in the PR/PI valuation (ERPNext reposts it), so no separate line.
    return local_pur, import_pur, pur_ret


def other_adjustments(co, fd, td, wh=None, cc_vnos=None):
    """
    Net SLE value change for EVERY voucher type that is neither a purchase
    (PR/PI/LCV) nor a sale (Delivery Note / Sales Invoice) — i.e. Stock Entry,
    Stock Reconciliation, repacks, etc.  Capturing this residual is what makes
    Opening + Purchases + Adjustments − Closing tie out to the GL COGS exactly.
    """
    j, c, p = _wh_base(co, wh)
    excl = PURCHASE_VTYPES + SALES_VTYPES
    ph_excl = ",".join(["%s"] * len(excl))

    vno = ""
    vp  = []
    if cc_vnos is not None:
        if cc_vnos:
            ph  = ",".join(["%s"] * len(cc_vnos))
            vno = "AND sle.voucher_no IN (" + ph + ")"
            vp  = list(cc_vnos)
        else:
            vno = "AND 1=0"

    where = " AND ".join(c + [
        "sle.posting_date BETWEEN %s AND %s",
        "sle.voucher_type NOT IN (" + ph_excl + ")",
    ])
    query = ("SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v "
             "FROM `tabStock Ledger Entry` sle " + j + " WHERE " + where + " " + vno)
    r = frappe.db.sql(query, p + [fd, td] + list(excl) + vp, as_dict=True)
    return flt(r[0].v) if r else 0.0


def non_cogs_sales_movement(co, fd, td, wh=None, cc=None, cc_vnos=None):
    """
    Delivery Note / Sales Invoice stock movements that did NOT post to a Cost of
    Goods Sold account — inter-warehouse transfers routed through an in-transit
    warehouse, samples, or write-offs booked elsewhere.  They reduce stock but are
    not COGS, so they belong in Adjustments, not in the sold figure.  Including them
    is what makes NET COGS tie exactly to the GL / Trial-Balance COGS.
    """
    j, c, p = _wh_base(co, wh)
    vno = ""; vp = []
    if cc_vnos is not None:
        if cc_vnos:
            ph  = ",".join(["%s"] * len(cc_vnos))
            vno = "AND sle.voucher_no IN (" + ph + ")"; vp = list(cc_vnos)
        else:
            vno = "AND 1=0"
    cc_sub = ""; ccp = []
    if cc:
        cc_sub = "AND gle.cost_center=%s"; ccp = [cc]
    where = " AND ".join(c + ["sle.posting_date BETWEEN %s AND %s",
                              "sle.voucher_type IN ('Delivery Note','Sales Invoice')"])
    query = (
        "SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v "
        "FROM `tabStock Ledger Entry` sle " + j + " "
        "WHERE " + where + " " + vno + " "
        "AND sle.voucher_no NOT IN ("
        "  SELECT gle.voucher_no FROM `tabGL Entry` gle "
        "  INNER JOIN `tabAccount` acc ON acc.name=gle.account "
        "  WHERE gle.company=%s AND gle.posting_date BETWEEN %s AND %s "
        "  AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND gle.is_cancelled=0 "
        "  AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold' " + cc_sub +
        ")"
    )
    r = frappe.db.sql(query, p + [fd, td] + vp + [co, fd, td] + ccp, as_dict=True)
    return flt(r[0].v) if r else 0.0


def sales_data(co, fd, td, cc=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    cc_cond = " AND gle.cost_center=%(cost_center)s" if cc else ""
    if cc: p["cost_center"] = cc
    query = ("SELECT COALESCE(SUM(gle.credit),0) AS gross, COALESCE(SUM(gle.debit),0) AS ret "
             "FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account "
             "WHERE gle.company=%(company)s AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s "
             "AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND gle.is_cancelled=0 "
             "AND acc.root_type='Income'" + cc_cond)
    r = frappe.db.sql(query, p, as_dict=True)
    g = flt(r[0].gross); ret = flt(r[0].ret)
    return g, ret, g - ret


def gl_cogs_total(co, fd, td, cc=None):
    """Trial-Balance COGS: movement on Cost-of-Goods-Sold accounts from sales."""
    p = {"company": co, "from_date": fd, "to_date": td}
    cc_cond = " AND gle.cost_center=%(cost_center)s" if cc else ""
    if cc: p["cost_center"] = cc
    query = ("SELECT COALESCE(SUM(gle.debit-gle.credit),0) AS v "
             "FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account "
             "WHERE gle.company=%(company)s AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s "
             "AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND gle.is_cancelled=0 "
             "AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold'" + cc_cond)
    r = frappe.db.sql(query, p, as_dict=True)
    return flt(r[0].v) if r else 0.0


def get_cc_vouchers(co, cc):
    rows = frappe.db.sql(
        "SELECT DISTINCT voucher_no FROM `tabGL Entry` WHERE company=%s AND cost_center=%s AND is_cancelled=0",
        (co, cc), as_list=True,
    )
    return [x[0] for x in rows]


def non_transit_warehouses(co):
    return frappe.db.sql_list("""
        SELECT name FROM `tabWarehouse`
        WHERE company=%s AND disabled=0
          AND (warehouse_type IS NULL OR warehouse_type!='Transit')
        ORDER BY name
    """, co)


def item_groups_with_activity(co, fd, td, wh=None):
    j, c, p = _wh_base(co, wh)
    where = " AND ".join(c + ["sle.posting_date<=%s"])
    query = ("SELECT DISTINCT itm.item_group "
             "FROM `tabStock Ledger Entry` sle " + j + " "
             "INNER JOIN `tabItem` itm ON itm.name=sle.item_code "
             "WHERE " + where + " AND sle.is_cancelled=0 ORDER BY itm.item_group")
    r = frappe.db.sql(query, p + [td], as_list=True)
    return [x[0] for x in r if x[0]]


# ── Item-group level figures (purchases from stock-increasing SLE) ────────────

def ig_figures(co, fd, td, wh, ig):
    j, c, p = _wh_base(co, wh)
    itm_j   = " INNER JOIN `tabItem` itm ON itm.name=sle.item_code"
    base_c  = " AND ".join(c)

    def s(date_cond, date_params):
        query = ("SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v "
                 "FROM `tabStock Ledger Entry` sle " + j + " " + itm_j + " "
                 "WHERE " + base_c + " AND itm.item_group=%s AND sle.is_cancelled=0 " + date_cond)
        r = frappe.db.sql(query, p + [ig] + date_params, as_dict=True)
        return flt(r[0].v) if r else 0.0

    opening_v = s("AND sle.posting_date<%s", [fd])

    pur_query = ("SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v "
                 "FROM `tabStock Ledger Entry` sle " + j + " " + itm_j + " "
                 "WHERE " + base_c + " AND itm.item_group=%s AND sle.is_cancelled=0 "
                 "AND sle.posting_date BETWEEN %s AND %s "
                 "AND sle.voucher_type IN ('Purchase Receipt','Purchase Invoice')")
    r_pur = frappe.db.sql(pur_query, p + [ig, fd, td], as_dict=True)
    net_pur_v = flt(r_pur[0].v) if r_pur else 0.0

    if getdate(td) >= getdate(today()):
        if wh:
            r = frappe.db.sql("""
                SELECT COALESCE(SUM(b.stock_value),0) AS v
                FROM `tabBin` b INNER JOIN `tabItem` itm ON itm.name=b.item_code
                WHERE b.warehouse=%s AND itm.item_group=%s
            """, [wh, ig], as_dict=True)
        else:
            r = frappe.db.sql("""
                SELECT COALESCE(SUM(b.stock_value),0) AS v
                FROM `tabBin` b INNER JOIN `tabWarehouse` w ON w.name=b.warehouse
                INNER JOIN `tabItem` itm ON itm.name=b.item_code
                WHERE w.company=%s AND w.disabled=0
                  AND (w.warehouse_type IS NULL OR w.warehouse_type!='Transit')
                  AND itm.item_group=%s
            """, [co, ig], as_dict=True)
        closing_v = flt(r[0].v) if r else 0.0
    else:
        closing_v = s("AND sle.posting_date<=%s", [td])

    r2 = frappe.db.sql("""
        SELECT
            COALESCE(SUM(CASE WHEN si.is_return=0 THEN sii.base_net_amount ELSE 0 END),0) AS gross,
            COALESCE(ABS(SUM(CASE WHEN si.is_return=1 THEN sii.base_net_amount ELSE 0 END)),0) AS ret
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name=sii.parent
        WHERE si.company=%s AND si.posting_date BETWEEN %s AND %s
          AND si.docstatus=1 AND sii.item_group=%s
    """, [co, fd, td, ig], as_dict=True)
    g_sales  = flt(r2[0].gross) if r2 else 0.0
    sal_ret  = flt(r2[0].ret)   if r2 else 0.0
    net_sale = g_sales - sal_ret

    formula_cogs = opening_v + net_pur_v - closing_v
    gross_profit = net_sale - formula_cogs
    return opening_v, net_pur_v, closing_v, formula_cogs, net_sale, gross_profit


# ── Row helpers ───────────────────────────────────────────────────────────────

def R(particulars, debit=0, credit=0, bold=False, indent=0, link=None, row_type="detail"):
    return {
        "particulars": particulars,
        "debit":       flt(debit, 3),
        "credit":      flt(credit, 3),
        "bold":        bold,
        "indent":      indent,
        "link":        link,
        "_row_type":   row_type,
    }

def S():
    return R("", row_type="divider")

def H(label):
    return R("── " + label + " " + "─" * (50 - len(label)), bold=True, row_type="recon_header")


# ── Main trading account section ──────────────────────────────────────────────

def build_main(co, fd, td, wh, cc):
    cc_vnos = get_cc_vouchers(co, cc) if cc else None
    op      = opening_stock(co, fd, wh)
    cl      = closing_stock(co, td, wh)
    local_pur, import_pur, pur_ret = purchase_split(co, fd, td, wh, cc_vnos)

    net_pur      = local_pur + import_pur - pur_ret
    goods_avail  = op + net_pur
    stock_cogs   = goods_avail - cl                      # plain trading formula: Opening + Purchases − Closing
    g_sales, sal_ret, net_sales = sales_data(co, fd, td, cc)
    gl_cogs      = gl_cogs_total(co, fd, td, cc)         # Trial-Balance COGS (the anchor)
    # Single balancing line to the Trial Balance. It absorbs every stock movement that is
    # not a purchase or a sale — Stock Entry / Reconciliation, opening-load, inter-warehouse
    # transfers via in-transit — plus the intrinsic per-voucher Stock-Ledger↔GL valuation
    # drift (moving-average shifts / backdated reposts). So NET COGS = the GL / TB figure.
    recon_tb     = flt(gl_cogs - stock_cogs, 3)
    # Accurate split of the reconciliation (adj_se + adj_tr + adj_val == recon_tb):
    adj_se  = flt(other_adjustments(co, fd, td, wh, cc_vnos), 3)             # Stock Entry / Reconciliation (opening-load, adjustments)
    adj_tr  = flt(non_cogs_sales_movement(co, fd, td, wh, cc, cc_vnos), 3)   # DN/SI stock out NOT booked to COGS (in-transit transfers)
    adj_val = flt(recon_tb - adj_se - adj_tr, 3)                             # residual: per-voucher Stock-Ledger ↔ GL valuation differences
    net_cogs     = gl_cogs                               # NET COGS mirrors the Trial Balance
    gross_profit = net_sales - net_cogs
    opening_date = str(add_days(fd, -1))
    currency     = frappe.db.get_value("Company", co, "default_currency") or ""

    rows = [
        R("SALES", bold=True, row_type="section"),
        R("Gross Sales Revenue",          credit=g_sales,   indent=1, link=_sr(co, fd, td)),
        R("Less: Returns / Credit Notes", debit=sal_ret,    indent=1, link=_sr(co, fd, td)),
        R("NET SALES",                    credit=net_sales, bold=True, row_type="net_sales"),
        S(),

        R("COST OF GOODS SOLD", bold=True, row_type="section"),
        R("Opening Stock", debit=op, indent=1,
          link=_sb(co, opening_date, opening_date, wh)),

        R("Purchases  (stock-increasing docs)", bold=True, indent=1),
    ]

    if local_pur:
        rows.append(R("Local Purchases  (PR/PI — company currency)",
                      debit=local_pur, indent=2,
                      link=_pse(co, fd, td, wh, ptype="Local")))
    if import_pur:
        rows.append(R("Import Purchases  (PR/PI — foreign currency or migrated IP)",
                      debit=import_pur, indent=2,
                      link=_pse(co, fd, td, wh, ptype="Import")))
    if pur_ret:
        rows.append(R("Less: Purchase Returns",
                      credit=pur_ret, indent=2,
                      link=_pse(co, fd, td, wh, ptype="Returns")))

    rows.append(R("Net Purchases",
                  debit=net_pur, bold=True, indent=1, row_type="subtotal",
                  link=_pse(co, fd, td, wh)))

    def _sgn(label, val, indent, link=None, bold=False, rt="detail"):
        return R(label, debit=(val if val >= 0 else 0), credit=(abs(val) if val < 0 else 0),
                 indent=indent, link=link, bold=bold, row_type=rt)

    rows += [
        R("Less: Closing Stock", credit=cl, indent=1, link=_sb(co, td, td, wh)),
        R("Stock-Movement COGS  (Opening + Purchases − Closing)",
          debit =stock_cogs if stock_cogs >= 0 else 0,
          credit=abs(stock_cogs) if stock_cogs <  0 else 0,
          bold=True, indent=1, row_type="subtotal", link=_sse(co, fd, td, wh)),
    ]

    # ── Reconciliation to Trial Balance — shown with its accurate 3-way split ────
    rows.append(_sgn("Reconciliation to Trial Balance", recon_tb, 1, bold=True, rt="subtotal"))
    if adj_se:
        rows.append(_sgn("Stock Entries & Reconciliations  (incl. opening-load)",
                         adj_se, 2, link=_sl(co, fd, td, wh)))
    if adj_tr:
        rows.append(_sgn("In-transit / Transfer-out  (Delivery Note — not COGS)",
                         adj_tr, 2, link=_sse(co, fd, td, wh)))
    if adj_val:
        rows.append(_sgn("Valuation & GL Differences  (Stock Ledger ↔ GL)",
                         adj_val, 2))

    rows += [
        R("NET COGS  (Trial Balance)",
          debit =net_cogs if net_cogs >= 0 else 0,
          credit=abs(net_cogs) if net_cogs <  0 else 0,
          bold=True, row_type="net_cogs", link=_sse(co, fd, td, wh)),
        R("NET COGS ties to Trial Balance COGS",
          bold=False, row_type="variance"),
        S(),

        R("GROSS PROFIT" if gross_profit >= 0 else "GROSS LOSS",
          debit =abs(gross_profit) if gross_profit <  0 else 0,
          credit=gross_profit       if gross_profit >= 0 else 0,
          bold=True, row_type="gross_profit"),
        S(),
    ]

    kv = {
        "opening":          op,
        "net_purchases":    net_pur,
        "closing":          cl,
        "stock_cogs":       stock_cogs,
        "recon_tb":         recon_tb,
        "formula_cogs":     net_cogs,   # chart/summary COGS = the Trial-Balance figure
        "gl_cogs":          gl_cogs,
        "net_sales":        net_sales,
        "gross_profit":     gross_profit,
        "gross_margin_pct": round(gross_profit / net_sales * 100, 1) if net_sales else 0.0,
        "currency":         currency,
    }
    return rows, kv


# ── Compact breakdown sections (parity with Audit; not wired in execute) ──────

def build_warehouse_breakdown(co, fd, td, cc):
    warehouses = non_transit_warehouses(co)
    if len(warehouses) <= 1:
        return []

    rows = [S(), H("BREAKDOWN BY WAREHOUSE")]
    for wh in warehouses:
        op   = opening_stock(co, fd, wh)
        cl   = closing_stock(co, td, wh)
        loc, imp, pur_ret = purchase_split(co, fd, td, wh)
        adj  = other_adjustments(co, fd, td, wh) + non_cogs_sales_movement(co, fd, td, wh)
        net_pur = loc + imp - pur_ret
        cogs    = flt(op + net_pur + adj - cl, 3)

        if op == 0 and net_pur == 0 and cl == 0:
            continue

        rows += [
            S(),
            R(wh, bold=True, indent=1, row_type="wh_header"),
            R("Opening Stock",      debit=op,      indent=2, link=_sb(co, str(add_days(fd, -1)), str(add_days(fd, -1)), wh)),
            R("Net Purchases",      debit=net_pur,  indent=2, link=_pse(co, fd, td, wh)),
            R("Closing Stock",      credit=cl,      indent=2, link=_sb(co, fd, td, wh)),
            R("NET COGS (Formula)", debit=cogs,     indent=2, bold=True, row_type="subtotal"),
        ]
    return rows


def build_item_group_breakdown(co, fd, td, wh, cc):
    groups = item_groups_with_activity(co, fd, td, wh)
    if not groups:
        return []

    rows = [S(), H("BREAKDOWN BY ITEM GROUP")]
    for ig in groups:
        op, net_pur, cl, cogs, net_sales, gp = ig_figures(co, fd, td, wh, ig)
        if op == 0 and net_pur == 0 and cl == 0 and net_sales == 0:
            continue
        rows += [
            S(),
            R(ig, bold=True, indent=1, row_type="wh_header"),
            R("Opening Stock",      debit=op,        indent=2),
            R("Net Purchases",      debit=net_pur,    indent=2),
            R("Closing Stock",      credit=cl,        indent=2),
            R("NET COGS (Formula)", debit=cogs,       indent=2, bold=True, row_type="subtotal"),
            R("Net Sales",          credit=net_sales, indent=2),
            R("Gross Profit",
              debit =gp if gp <  0 else 0,
              credit=gp if gp >= 0 else 0,
              bold=True, indent=2, row_type="gross_profit"),
        ]
    return rows


# ── Chart and summary ─────────────────────────────────────────────────────────

def _make_chart(kv):
    op   = flt(kv.get("opening", 0), 2)
    pur  = flt(kv.get("net_purchases", 0), 2)
    cl   = flt(kv.get("closing", 0), 2)
    cogs = flt(kv.get("formula_cogs", 0), 2)
    ns   = flt(kv.get("net_sales", 0), 2)
    gp   = flt(kv.get("gross_profit", 0), 2)

    return {
        "data": {
            "labels": ["Opening Stock", "Net Purchases", "Less Closing", "Formula COGS", "Net Sales", "Gross Profit"],
            "datasets": [
                {"name": "Stock Flow", "values": [op,  pur, cl,   cogs, 0,           0         ]},
                {"name": "P & L",      "values": [0,   0,   0,    0,    ns, max(gp, 0)          ]},
            ],
        },
        "type": "bar",
        "colors": ["#1565c0", "#2e7d32"],
        "fieldtype": "Currency",
    }


def _make_summary(kv):
    ns   = kv.get("net_sales", 0)
    cogs = kv.get("formula_cogs", 0)   # = Trial-Balance COGS
    rec  = kv.get("recon_tb", 0)
    gp   = kv.get("gross_profit", 0)
    pct  = kv.get("gross_margin_pct", 0)
    cur  = kv.get("currency", "")
    return [
        {"value": ns,   "label": "Net Sales",         "datatype": "Currency", "currency": cur, "indicator": "Blue"},
        {"value": cogs, "label": "COGS (Trial Bal.)", "datatype": "Currency", "currency": cur, "indicator": "Orange"},
        {"value": rec,  "label": "Recon to TB",       "datatype": "Currency", "currency": cur, "indicator": "Grey"},
        {"value": gp,   "label": "Gross Profit",      "datatype": "Currency", "currency": cur,
         "indicator": "Green" if gp >= 0 else "Red"},
        {"value": pct,  "label": "Gross Margin %",    "datatype": "Percent",
         "indicator": "Green" if gp >= 0 else "Red"},
    ]
