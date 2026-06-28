"""
Audit Trading Account Report — Perpetual Inventory
Concise single-page trading account; optional breakdown by Warehouse or Item Group.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, today, add_days
from urllib.parse import urlencode


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()

    co = filters.company
    fd = filters.get("from_date")
    td = filters.get("to_date")

    if not co or not fd or not td:
        return columns, [], None, None, None

    fd = str(fd); td = str(td)
    wh        = filters.get("warehouse")
    cc        = filters.get("cost_center")
    breakdown = filters.get("breakdown_by") or ""

    rows, kv = build_main(co, fd, td, wh, cc)

    if breakdown == "Warehouse" and not wh:
        rows += build_warehouse_breakdown(co, fd, td, cc)
    elif breakdown == "Item Group":
        rows += build_item_group_breakdown(co, fd, td, wh, cc)

    return columns, rows, None, _make_chart(kv), _make_summary(kv)


def get_columns():
    return [
        {"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data",     "width": 380},
        {"label": _("Dr"),          "fieldname": "debit",       "fieldtype": "Currency",  "width": 170},
        {"label": _("Cr"),          "fieldname": "credit",      "fieldtype": "Currency",  "width": 170},
    ]


# ── URL helpers ───────────────────────────────────────────────────────────────

def _url(report, params):
    return f"/app/query-report/{report.replace(' ', '%20')}?{urlencode(params)}"

def _sl(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Stock Ledger", p)

def _sb(co, date, wh=None):
    p = {"company": co, "date": str(date)}
    if wh: p["warehouse"] = wh
    return _url("Stock Balance", p)

def _sr(co, fd, td):
    return _url("Sales Register", {"company": co, "from_date": fd, "to_date": td})


# ── SLE / GL aggregation ──────────────────────────────────────────────────────

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
    r = frappe.db.sql(
        f"SELECT {select} FROM `tabStock Ledger Entry` sle {j} WHERE {where}",
        p + extra_params, as_dict=True,
    )
    return r


def opening_stock(co, fd, wh=None):
    """
    Cumulative SLE before from_date PLUS any Stock Reconciliation (purpose=Opening Stock)
    posted within the period — those represent opening balance loads, not period adjustments.
    """
    j, c, p = _wh_base(co, wh)
    where = " AND ".join(c)
    r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v
        FROM `tabStock Ledger Entry` sle {j}
        LEFT JOIN `tabStock Reconciliation` sr
            ON sr.name=sle.voucher_no AND sle.voucher_type='Stock Reconciliation'
        WHERE {where}
          AND (sle.posting_date < %s
               OR (sle.voucher_type='Stock Reconciliation'
                   AND COALESCE(sr.purpose,'')='Opening Stock'))
    """, p + [fd], as_dict=True)
    return flt(r[0].v) if r else 0.0


def stock_recon_adjustment(co, fd, td, wh=None):
    """
    Net Stock Reconciliation (purpose != Opening Stock) within the period.
    Positive = excess found; Negative = shortage / write-off.
    Opening Stock purpose reconciliations are excluded — they belong in opening_stock().
    """
    j, c, p = _wh_base(co, wh)
    where = " AND ".join(c)
    r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v
        FROM `tabStock Ledger Entry` sle {j}
        LEFT JOIN `tabStock Reconciliation` sr
            ON sr.name=sle.voucher_no AND sle.voucher_type='Stock Reconciliation'
        WHERE {where}
          AND sle.posting_date BETWEEN %s AND %s
          AND sle.voucher_type='Stock Reconciliation'
          AND COALESCE(sr.purpose,'')!='Opening Stock'
    """, p + [fd, td], as_dict=True)
    return flt(r[0].v) if r else 0.0


def closing_stock(co, td, wh=None):
    if getdate(td) >= getdate(today()):
        if wh:
            r = frappe.db.sql(
                "SELECT COALESCE(SUM(actual_qty*valuation_rate),0) AS v FROM `tabBin` WHERE warehouse=%s",
                wh, as_dict=True)
        else:
            r = frappe.db.sql("""
                SELECT COALESCE(SUM(b.actual_qty*b.valuation_rate),0) AS v
                FROM `tabBin` b INNER JOIN `tabWarehouse` w ON w.name=b.warehouse
                WHERE w.company=%s AND w.disabled=0
                  AND (w.warehouse_type IS NULL OR w.warehouse_type!='Transit')
            """, co, as_dict=True)
        return flt(r[0].v) if r else 0.0
    r = _sle(co, wh,
             ["sle.posting_date<=%s"],
             [td],
             "COALESCE(SUM(sle.stock_value_difference),0) AS v")
    return flt(r[0].v) if r else 0.0


def purchase_split(co, fd, td, wh=None, cc_vnos=None):
    """Returns (local_pr, import_pr, lcv, pi_adj, pur_ret) all in base currency."""
    company_cur = frappe.db.get_value("Company", co, "default_currency") or ""
    j, c, p = _wh_base(co, wh)

    vno = ""
    vp  = []
    if cc_vnos is not None:
        if not cc_vnos:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        ph  = ",".join(["%s"]*len(cc_vnos))
        vno = f" AND sle.voucher_no IN ({ph})"
        vp  = list(cc_vnos)

    base = " AND ".join(c) + f" AND sle.posting_date BETWEEN %s AND %s {vno}"
    bp   = p + [fd, td] + vp

    def q(extra_join, extra_where, extra_params, agg="SUM(sle.stock_value_difference)"):
        r = frappe.db.sql(
            f"SELECT COALESCE({agg},0) AS v "
            f"FROM `tabStock Ledger Entry` sle {j} {extra_join} "
            f"WHERE {base} AND {extra_where} AND sle.is_cancelled=0",
            bp + extra_params, as_dict=True,
        )
        return flt(r[0].v) if r else 0.0

    local_pr  = q("INNER JOIN `tabPurchase Receipt` pr ON pr.name=sle.voucher_no",
                  "sle.voucher_type='Purchase Receipt' AND pr.is_return=0 AND sle.stock_value_difference>0 AND pr.currency=%s",
                  [company_cur])
    import_pr = q("INNER JOIN `tabPurchase Receipt` pr ON pr.name=sle.voucher_no",
                  "sle.voucher_type='Purchase Receipt' AND pr.is_return=0 AND sle.stock_value_difference>0 AND pr.currency!=%s",
                  [company_cur])
    lcv       = q("", "sle.voucher_type='Landed Cost Voucher'", [])
    pi_adj    = q("INNER JOIN `tabPurchase Invoice` pi ON pi.name=sle.voucher_no",
                  "sle.voucher_type='Purchase Invoice' AND pi.is_return=0", [])
    pur_ret   = abs(q(
        "LEFT JOIN `tabPurchase Receipt` pr ON pr.name=sle.voucher_no AND sle.voucher_type='Purchase Receipt' "
        "LEFT JOIN `tabPurchase Invoice` pi ON pi.name=sle.voucher_no AND sle.voucher_type='Purchase Invoice'",
        "sle.stock_value_difference<0 AND ((sle.voucher_type='Purchase Receipt' AND pr.is_return=1) OR (sle.voucher_type='Purchase Invoice' AND pi.is_return=1))",
        []))
    return local_pr, import_pr, lcv, pi_adj, pur_ret


def sales_data(co, fd, td, cc=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    cc_cond = " AND gle.cost_center=%(cost_center)s" if cc else ""
    if cc: p["cost_center"] = cc
    r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(gle.credit),0) AS gross, COALESCE(SUM(gle.debit),0) AS ret
        FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account
        WHERE gle.company=%(company)s AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND gle.is_cancelled=0
          AND acc.root_type='Income' {cc_cond}
    """, p, as_dict=True)
    g = flt(r[0].gross); ret = flt(r[0].ret)
    return g, ret, g - ret


def gl_cogs_total(co, fd, td, cc=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    cc_cond = " AND gle.cost_center=%(cost_center)s" if cc else ""
    if cc: p["cost_center"] = cc
    r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(gle.debit-gle.credit),0) AS v
        FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account
        WHERE gle.company=%(company)s AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND gle.voucher_type IN ('Sales Invoice','Delivery Note') AND gle.is_cancelled=0
          AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold' {cc_cond}
    """, p, as_dict=True)
    return flt(r[0].v) if r else 0.0


def stock_gl_balance(co):
    accts = frappe.db.sql_list("""
        SELECT DISTINCT w.account FROM `tabWarehouse` w
        WHERE w.company=%s AND w.account IS NOT NULL AND w.account!=''
          AND (w.warehouse_type IS NULL OR w.warehouse_type!='Transit')
    """, co)
    if not accts:
        return 0.0
    ph = ",".join(["%s"]*len(accts))
    r = frappe.db.sql(
        f"SELECT COALESCE(SUM(debit-credit),0) AS v FROM `tabGL Entry` "
        f"WHERE account IN ({ph}) AND is_cancelled=0",
        accts, as_dict=True,
    )
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
    r = frappe.db.sql(f"""
        SELECT DISTINCT itm.item_group
        FROM `tabStock Ledger Entry` sle {j}
        INNER JOIN `tabItem` itm ON itm.name=sle.item_code
        WHERE {where} AND sle.is_cancelled=0
        ORDER BY itm.item_group
    """, p + [td], as_list=True)
    return [x[0] for x in r if x[0]]


# ── Item-group level figures ──────────────────────────────────────────────────

def ig_figures(co, fd, td, wh, ig):
    j, c, p = _wh_base(co, wh)
    itm_j   = " INNER JOIN `tabItem` itm ON itm.name=sle.item_code"
    base_c  = " AND ".join(c)

    def s(date_cond, date_params, extra_vt):
        agg = "SUM(sle.stock_value_difference)"
        vt_clause = (f" AND sle.voucher_type IN ({','.join(['%s']*len(extra_vt))})"
                     if extra_vt else "")
        r = frappe.db.sql(
            f"SELECT COALESCE({agg},0) AS v "
            f"FROM `tabStock Ledger Entry` sle {j} {itm_j} "
            f"WHERE {base_c} AND itm.item_group=%s AND sle.is_cancelled=0"
            f" {date_cond}{vt_clause}",
            p + [ig] + date_params + list(extra_vt), as_dict=True,
        )
        return flt(r[0].v) if r else 0.0

    opening_v = s("AND sle.posting_date<%s", [fd], [])
    net_pur_v = s("AND sle.posting_date BETWEEN %s AND %s", [fd, td],
                  ["Purchase Receipt", "Landed Cost Voucher", "Purchase Invoice"])

    if getdate(td) >= getdate(today()):
        if wh:
            r = frappe.db.sql("""
                SELECT COALESCE(SUM(b.actual_qty*b.valuation_rate),0) AS v
                FROM `tabBin` b INNER JOIN `tabItem` itm ON itm.name=b.item_code
                WHERE b.warehouse=%s AND itm.item_group=%s
            """, [wh, ig], as_dict=True)
        else:
            r = frappe.db.sql("""
                SELECT COALESCE(SUM(b.actual_qty*b.valuation_rate),0) AS v
                FROM `tabBin` b INNER JOIN `tabWarehouse` w ON w.name=b.warehouse
                INNER JOIN `tabItem` itm ON itm.name=b.item_code
                WHERE w.company=%s AND w.disabled=0
                  AND (w.warehouse_type IS NULL OR w.warehouse_type!='Transit')
                  AND itm.item_group=%s
            """, [co, ig], as_dict=True)
        closing_v = flt(r[0].v) if r else 0.0
    else:
        closing_v = s("AND sle.posting_date<=%s", [td], [])

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
    return R(f"── {label} {'─'*(50-len(label))}", bold=True, row_type="recon_header")


# ── Main trading account section ──────────────────────────────────────────────

def build_main(co, fd, td, wh, cc):
    cc_vnos = get_cc_vouchers(co, cc) if cc else None
    op      = opening_stock(co, fd, wh)
    cl      = closing_stock(co, td, wh)
    recon   = stock_recon_adjustment(co, fd, td, wh)
    loc, imp, lcv, pi_adj, pur_ret = purchase_split(co, fd, td, wh, cc_vnos)
    net_pur      = loc + imp + lcv + pi_adj - pur_ret
    goods_avail  = op + net_pur
    formula_cogs = goods_avail + recon - cl
    g_sales, sal_ret, net_sales = sales_data(co, fd, td, cc)
    gl_cogs      = gl_cogs_total(co, fd, td, cc)
    gross_profit = net_sales - formula_cogs
    cogs_var     = flt(formula_cogs - gl_cogs, 3)
    bin_val      = closing_stock(co, td)
    gl_stock     = stock_gl_balance(co)
    bin_gl_var   = flt(bin_val - gl_stock, 3)
    opening_date = str(add_days(fd, -1))
    currency     = frappe.db.get_value("Company", co, "default_currency") or ""

    rows = [
        R("SALES", bold=True, row_type="section"),
        R("Gross Sales Revenue",          credit=g_sales,    indent=1, link=_sr(co, fd, td)),
        R("Less: Returns / Credit Notes", debit=sal_ret,     indent=1, link=_sr(co, fd, td)),
        R("NET SALES",                    credit=net_sales,  bold=True, row_type="net_sales"),
        S(),
        R("COST OF GOODS SOLD", bold=True, row_type="section"),
        R("Opening Stock", debit=op, indent=1, link=_sb(co, opening_date, wh)),
    ]

    if loc:
        rows.append(R("    Local Purchases  (PR — company currency)",  debit=loc, indent=2, link=_sl(co, fd, td, wh)))
    if imp:
        rows.append(R("    Import Purchases  (PR — foreign currency)", debit=imp, indent=2, link=_sl(co, fd, td, wh)))
    if lcv:
        rows.append(R("    Landed Cost Vouchers",                      debit=lcv, indent=2, link=_sl(co, fd, td, wh)))
    if pi_adj:
        rows.append(R("    PI Rate Adjustment",
                      debit=pi_adj  if pi_adj > 0 else 0,
                      credit=abs(pi_adj) if pi_adj < 0 else 0,
                      indent=2))
    if pur_ret:
        rows.append(R("Less: Purchase Returns", credit=pur_ret, indent=1, link=_sl(co, fd, td, wh)))

    rows += [
        R("Net Purchases",            debit=net_pur,     bold=True, indent=1, row_type="subtotal"),
        R("Goods Available for Sale", debit=goods_avail, indent=1),
    ]

    if recon:
        if recon > 0:
            rows.append(R("Stock Reconciliation  (Excess Found)",   debit=recon,        indent=1, link=_sl(co, fd, td, wh)))
        else:
            rows.append(R("Stock Reconciliation  (Shortage / Write-off)", credit=abs(recon), indent=1, link=_sl(co, fd, td, wh)))

    rows += [
        R("Less: Closing Stock",      credit=cl,          indent=1, link=_sb(co, td, wh)),
        R("NET COGS",                 debit=formula_cogs, bold=True, row_type="net_cogs"),
        S(),
        R("GROSS PROFIT",
          debit =gross_profit if gross_profit <  0 else 0,
          credit=gross_profit if gross_profit >= 0 else 0,
          bold=True, row_type="gross_profit"),
        S(),
        H("GL RECONCILIATION"),
        R("Perpetual GL COGS  (Dr on Cost of Goods Sold a/c)", debit=gl_cogs,       indent=1),
        R("Formula COGS  (Opening + Purchases − Closing)",      debit=formula_cogs,  indent=1),
        {**R("COGS Variance  ← must be zero",
             debit =cogs_var if cogs_var >  0.005 else 0,
             credit=abs(cogs_var) if cogs_var < -0.005 else 0,
             bold=True, indent=1, row_type="variance",
             link=_url("Item COGS Analysis Report", {"company": co, "from_date": fd, "to_date": td})),
         "_is_variance": True, "_clean": abs(cogs_var) <= 0.005},
        {**R("Bin vs Stock Account GL  ← must be zero",
             debit =bin_gl_var if bin_gl_var >  0.005 else 0,
             credit=abs(bin_gl_var) if bin_gl_var < -0.005 else 0,
             bold=True, indent=1, row_type="variance",
             link=_url("Stock Balance", {"company": co, "date": td})),
         "_is_variance": True, "_clean": abs(bin_gl_var) <= 0.005},
    ]

    kv = {
        "opening":          op,
        "net_purchases":    net_pur,
        "closing":          cl,
        "formula_cogs":     formula_cogs,
        "net_sales":        net_sales,
        "gross_profit":     gross_profit,
        "gl_cogs":          gl_cogs,
        "gross_margin_pct": round(gross_profit / net_sales * 100, 1) if net_sales else 0.0,
        "currency":         currency,
    }
    return rows, kv


# ── Compact breakdown sections ────────────────────────────────────────────────

def build_warehouse_breakdown(co, fd, td, cc):
    warehouses = non_transit_warehouses(co)
    if len(warehouses) <= 1:
        return []

    rows = [S(), H("BREAKDOWN BY WAREHOUSE")]
    for wh in warehouses:
        op   = opening_stock(co, fd, wh)
        cl   = closing_stock(co, td, wh)
        loc, imp, lcv, pi_adj, pur_ret = purchase_split(co, fd, td, wh)
        net_pur = loc + imp + lcv + pi_adj - pur_ret
        cogs    = flt(op + net_pur - cl, 3)

        if op == 0 and net_pur == 0 and cl == 0:
            continue

        rows += [
            S(),
            R(wh, bold=True, indent=1, row_type="wh_header"),
            R("Opening Stock",      debit=op,      indent=2, link=_sb(co, str(add_days(fd, -1)), wh)),
            R("Net Purchases",      debit=net_pur,  indent=2, link=_sl(co, fd, td, wh)),
            R("Closing Stock",      credit=cl,      indent=2, link=_sb(co, td, wh)),
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
    cogs = kv.get("formula_cogs", 0)
    gp   = kv.get("gross_profit", 0)
    pct  = kv.get("gross_margin_pct", 0)
    cur  = kv.get("currency", "")
    return [
        {"value": ns,   "label": "Net Sales",    "datatype": "Currency", "currency": cur, "indicator": "Blue"},
        {"value": cogs, "label": "COGS",          "datatype": "Currency", "currency": cur, "indicator": "Orange"},
        {"value": gp,   "label": "Gross Profit",  "datatype": "Currency", "currency": cur,
         "indicator": "Green" if gp >= 0 else "Red"},
        {"value": pct,  "label": "Gross Margin %","datatype": "Percent",
         "indicator": "Green" if gp >= 0 else "Red"},
    ]
