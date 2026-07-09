"""
Audit Trading Account Report — Perpetual Inventory
Concise single-page trading account; optional breakdown by Warehouse or Item Group.
"""
import json

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


def _pi_list(co, fd, td, company_cur, kind):
    """List-view drill-down: all Purchase Invoices behind a purchase row."""
    p = {
        "company": co,
        "posting_date": json.dumps(["between", [fd, td]]),
        "docstatus": 1,
    }
    if kind == "local":
        p["currency"] = company_cur
        p["is_return"] = 0
    elif kind == "import":
        p["currency"] = json.dumps(["!=", company_cur])
        p["is_return"] = 0
    elif kind == "return":
        p["is_return"] = 1
    return f"/app/purchase-invoice?{urlencode(p)}"


def _lcv_list(co, fd, td):
    p = {
        "company": co,
        "posting_date": json.dumps(["between", [fd, td]]),
        "docstatus": 1,
    }
    return f"/app/landed-cost-voucher?{urlencode(p)}"


def lcv_charges(co, fd, td):
    """Total Landed Cost Voucher charges in the period (already baked into
    item valuation / purchase figures above via repost — informational)."""
    r = frappe.db.sql("""
        SELECT COALESCE(SUM(total_taxes_and_charges), 0) AS v
        FROM `tabLanded Cost Voucher`
        WHERE company=%s AND posting_date BETWEEN %s AND %s AND docstatus=1
    """, (co, fd, td), as_dict=True)
    return flt(r[0].v) if r else 0.0


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
    """Opening stock = closing stock as of the day before from_date (Tally convention)."""
    return closing_stock(co, str(add_days(fd, -1)), wh)


def stock_recon_adjustment(co, fd, td, wh=None):
    """
    Net Stock Reconciliation within the period (all purposes).
    Positive = excess found / opening load; Negative = shortage / write-off.
    """
    j, c, p = _wh_base(co, wh)
    where = " AND ".join(c)
    r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(sle.stock_value_difference),0) AS v
        FROM `tabStock Ledger Entry` sle {j}
        WHERE {where}
          AND sle.posting_date BETWEEN %s AND %s
          AND sle.voucher_type='Stock Reconciliation'
          AND sle.is_cancelled=0
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
    """
    Purchase breakdown for stocked items (is_stock_item=1) only.

    With update stock (SLE — PI with update_stock=1 only):
        local_pur, import_pur  — by currency
        lcv                    — LCV linked to PI-with-update-stock
        pur_ret                — returns (PI credit notes)

    Without update stock (PI with update_stock=0, stocked items):
        pi_no_local, pi_no_import — by currency
        pi_no_lcv                 — LCV linked to those PI-without-update-stock
        pi_no_ret                 — returns
    """
    company_cur = frappe.db.get_value("Company", co, "default_currency") or ""
    j, c, p = _wh_base(co, wh)

    vno = ""
    vp  = []
    if cc_vnos is not None:
        if not cc_vnos:
            return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        ph  = ",".join(["%s"]*len(cc_vnos))
        vno = f" AND sle.voucher_no IN ({ph})"
        vp  = list(cc_vnos)

    base = " AND ".join(c) + f" AND sle.posting_date BETWEEN %s AND %s {vno}"
    bp   = p + [fd, td] + vp

    # ── SLE-based purchases (Purchase Invoice with update_stock=1), by currency ─
    sle_rows = frappe.db.sql(
        f"""SELECT
                COALESCE(pi.currency, %s)                        AS cur,
                COALESCE(SUM(CASE WHEN sle.stock_value_difference > 0
                             THEN sle.stock_value_difference ELSE 0 END), 0) AS gross,
                COALESCE(ABS(SUM(CASE WHEN sle.stock_value_difference < 0
                             THEN sle.stock_value_difference ELSE 0 END)), 0) AS ret
            FROM `tabStock Ledger Entry` sle {j}
            INNER JOIN `tabItem` itm
                ON itm.name=sle.item_code AND itm.is_stock_item=1
            INNER JOIN `tabPurchase Invoice` pi
                ON pi.name=sle.voucher_no
            WHERE {base}
              AND sle.voucher_type='Purchase Invoice'
              AND sle.is_cancelled=0
            GROUP BY cur""",
        [company_cur] + bp, as_dict=True,
    )

    local_pur = import_pur = pur_ret = 0.0
    for row in sle_rows:
        is_foreign = (row.cur or company_cur) != company_cur
        if is_foreign:
            import_pur += flt(row.gross)
        else:
            local_pur  += flt(row.gross)
        pur_ret += flt(row.ret)

    # Subquery to identify LCVs linked to PI-without-update-stock
    _pi_no_lcv_subq = """
        SELECT 1 FROM `tabLanded Cost Purchase Receipt` lcpr
        INNER JOIN `tabPurchase Invoice` pi2
            ON pi2.name=lcpr.receipt_document
            AND lcpr.receipt_document_type='Purchase Invoice'
            AND pi2.update_stock=0
        WHERE lcpr.parent=sle.voucher_no
    """

    # ── LCV linked to PR / PI-with-update-stock ───────────────────────────────
    lcv_r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS v
        FROM `tabStock Ledger Entry` sle {j}
        INNER JOIN `tabItem` itm ON itm.name=sle.item_code AND itm.is_stock_item=1
        WHERE {base}
          AND sle.voucher_type='Landed Cost Voucher'
          AND sle.is_cancelled=0
          AND NOT EXISTS ({_pi_no_lcv_subq})
    """, bp, as_dict=True)
    lcv = flt(lcv_r[0].v) if lcv_r else 0.0

    # ── LCV linked to PI-without-update-stock ─────────────────────────────────
    pi_no_lcv_r = frappe.db.sql(f"""
        SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS v
        FROM `tabStock Ledger Entry` sle {j}
        INNER JOIN `tabItem` itm ON itm.name=sle.item_code AND itm.is_stock_item=1
        WHERE {base}
          AND sle.voucher_type='Landed Cost Voucher'
          AND sle.is_cancelled=0
          AND EXISTS ({_pi_no_lcv_subq})
    """, bp, as_dict=True)
    pi_no_lcv = flt(pi_no_lcv_r[0].v) if pi_no_lcv_r else 0.0

    # ── PI without update_stock, stocked items — local/import from PI table ───
    wh_clause_no = "AND pii.warehouse=%s" if wh else ""
    wh_param_no  = [wh] if wh else []

    vno_pi = ""
    vp_pi  = []
    if cc_vnos is not None:
        if cc_vnos:
            ph     = ",".join(["%s"]*len(cc_vnos))
            vno_pi = f"AND pi.name IN ({ph})"
            vp_pi  = list(cc_vnos)
        else:
            vno_pi = "AND 1=0"

    pi_no_rows = frappe.db.sql(f"""
        SELECT
            COALESCE(pi.currency, %s)                                              AS cur,
            COALESCE(SUM(CASE WHEN pi.is_return=0 THEN pii.base_net_amount ELSE 0 END), 0) AS gross,
            COALESCE(ABS(SUM(CASE WHEN pi.is_return=1 THEN pii.base_net_amount ELSE 0 END)), 0) AS ret
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi  ON pi.name=pii.parent
        INNER JOIN `tabItem`             itm ON itm.name=pii.item_code
        WHERE pi.company=%s
          AND pi.posting_date BETWEEN %s AND %s
          AND pi.docstatus=1
          AND pi.update_stock=0
          AND itm.is_stock_item=1
          {wh_clause_no} {vno_pi}
        GROUP BY pi.currency
    """, [company_cur, co, fd, td] + wh_param_no + vp_pi, as_dict=True)

    pi_no_local = pi_no_import = pi_no_ret = 0.0
    for row in pi_no_rows:
        is_foreign = (row.cur or company_cur) != company_cur
        if is_foreign:
            pi_no_import += flt(row.gross)
        else:
            pi_no_local  += flt(row.gross)
        pi_no_ret += flt(row.ret)

    return (local_pur, import_pur, lcv, pur_ret,
            pi_no_local, pi_no_import, pi_no_lcv, pi_no_ret)


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
    (local_pur, import_pur, lcv, pur_ret,
     pi_no_local, pi_no_import, pi_no_lcv, pi_no_ret) = purchase_split(co, fd, td, wh, cc_vnos)

    net_pur      = local_pur + import_pur + lcv - pur_ret
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

    pi_no_net = pi_no_local + pi_no_import + pi_no_lcv - pi_no_ret

    rows = [
        R("SALES", bold=True, row_type="section"),
        R("Gross Sales Revenue",          credit=g_sales,   indent=1, link=_sr(co, fd, td)),
        R("Less: Returns / Credit Notes", debit=sal_ret,    indent=1, link=_sr(co, fd, td)),
        R("NET SALES",                    credit=net_sales, bold=True, row_type="net_sales"),
        S(),

        R("COST OF GOODS SOLD", bold=True, row_type="section"),
        R("Opening Stock", debit=op, indent=1, link=_sb(co, opening_date, wh)),

        # ── Purchases with update stock ───────────────────────────────────────
        R("Purchases  ← PI  (with Update Stock)", bold=True, indent=1),
    ]

    lcv_chg = lcv_charges(co, fd, td)

    if local_pur:
        rows.append(R("Local Purchases",
                      debit=local_pur, indent=2, link=_pi_list(co, fd, td, currency, "local")))
    if import_pur:
        rows.append(R("Import Purchases  (foreign currency)",
                      debit=import_pur, indent=2, link=_pi_list(co, fd, td, currency, "import")))
    if lcv:
        rows.append(R("Landed Cost Vouchers",
                      debit=lcv, indent=2, link=_lcv_list(co, fd, td)))
    if lcv_chg and not lcv:
        rows.append(R("of which: Landed Cost Charges  (freight/customs — included above)",
                      debit=lcv_chg, indent=3, link=_lcv_list(co, fd, td)))
    if pur_ret:
        rows.append(R("Less: Returns",
                      credit=pur_ret, indent=2, link=_pi_list(co, fd, td, currency, "return")))

    rows.append(R("Net Purchases  (with Update Stock)",
                  debit=net_pur, bold=True, indent=1, row_type="subtotal"))

    # ── Purchases without update stock (stocked items — shown for visibility) ─
    rows.append(R("Purchases  ← PI  (without Update Stock, stocked items)", bold=True, indent=1))

    if pi_no_local:
        rows.append(R("Local Purchases",   debit=pi_no_local,  indent=2,
                      link=_pi_list(co, fd, td, currency, "local")))
    if pi_no_import:
        rows.append(R("Import Purchases  (foreign currency)", debit=pi_no_import, indent=2,
                      link=_pi_list(co, fd, td, currency, "import")))
    if pi_no_lcv:
        rows.append(R("Landed Cost Vouchers", debit=pi_no_lcv, indent=2,
                      link=_lcv_list(co, fd, td)))
    if pi_no_ret:
        rows.append(R("Less: Returns", credit=pi_no_ret, indent=2,
                      link=_pi_list(co, fd, td, currency, "return")))

    rows.append(R("Net Purchases  (without Update Stock)",
                  debit=pi_no_net, bold=True, indent=1, row_type="subtotal"))

    # ── COGS formula continues with SLE-based goods available ─────────────────
    rows.append(R("Goods Available for Sale", debit=goods_avail, indent=1))

    if recon:
        if recon > 0:
            rows.append(R("Stock Reconciliation  (Excess Found / Opening Load)",
                          debit=recon, indent=1, link=_sl(co, fd, td, wh)))
        else:
            rows.append(R("Stock Reconciliation  (Shortage / Write-off)",
                          credit=abs(recon), indent=1, link=_sl(co, fd, td, wh)))

    rows += [
        R("Less: Closing Stock", credit=cl,          indent=1, link=_sb(co, td, wh)),
        R("NET COGS",            debit=formula_cogs, bold=True, row_type="net_cogs"),
        S(),
        R("GROSS PROFIT",
          debit =gross_profit if gross_profit <  0 else 0,
          credit=gross_profit if gross_profit >= 0 else 0,
          bold=True, row_type="gross_profit"),
        S(),
    ]

    # ── GL Reconciliation ─────────────────────────────────────────────────────
    rows += [
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
        loc, imp, lcv, pur_ret, _a, _b, _c, _d = purchase_split(co, fd, td, wh)
        net_pur = loc + imp + lcv - pur_ret
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
