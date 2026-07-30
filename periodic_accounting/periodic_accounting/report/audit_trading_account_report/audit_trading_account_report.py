"""
Audit Trading Account Report — Perpetual Inventory
Concise single-page trading account; optional breakdown by Warehouse or Item Group.
"""
import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, today, add_days
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
    wh = filters.get("warehouse")
    # A group warehouse (e.g. "All Warehouses") holds no direct SLE/Bin rows — those
    # live on its leaf children. Treat a group selection as company-wide so totals
    # match the Stock Balance report instead of returning 0.
    if wh and frappe.db.get_value("Warehouse", wh, "is_group"):
        wh = None
    cc = filters.get("cost_center")

    rows, kv = build_main(
        co, fd, td, wh, cc,
        merge_adj=cint(filters.get("merge_stock_adjustments")),
        # default when the filter is absent (API / scheduled runs) matches the form's default
        received_basis=(filters.get("cogs_basis") or "Per Goods Received") == "Per Goods Received",
    )
    return columns, rows, _formula_note(kv), _make_chart(kv), _make_summary(kv)


def _formula_note(kv):
    """The formula the NET COGS line is computed from, with this period's figures substituted.

    Printed above the table so a reader never has to be told verbally how the figure was reached,
    and so the definition of the Purchases line - invoices, not goods received - is on the page
    next to the number it produces.
    """
    def m(v):
        return "{:,.3f}".format(flt(v, 3))

    return _(
        "<div style='padding:10px 12px;border-left:3px solid #1f6f54;background:#f4f9f7;"
        "margin-bottom:10px;line-height:1.55'>"
        "<b>Net COGS (Trading Formula)</b> = Opening Stock + Purchases &plusmn; Stock Adjustments "
        "&minus; Closing Stock<br>"
        "<span style='font-family:monospace'>{op} + {pur} {sign} {adj} &minus; {cl} = "
        "<b>{cogs}</b></span> {ccy}  &nbsp;&nbsp;{grni_note}<br>"
        "<span style='color:#555'>Purchases are Purchase Invoices dated in this period, goods "
        "lines only, excluding VAT, so the line ties to the Purchase Register. Goods received "
        "whose supplier invoice is not yet posted are already inside Closing Stock but are not in "
        "Purchases, so they appear under Reconciliation to Trial Balance and can be drilled to the "
        "receipts concerned. Stock "
        "Adjustments covers Stock Reconciliations and Stock Entries, being the stock movements "
        "that are neither a purchase nor a sale.</span></div>"
    ).format(
        op=m(kv.get("opening")), pur=m(kv.get("net_purchases")),
        grni_note=(
            _("Purchases are stated <b>per goods received</b>: they include {0} received but "
              "not yet invoiced.").format(m(kv.get("grni")))
            if kv.get("received_basis")
            else _("plus Goods Received Not Yet Invoiced {0} under Reconciliation to Trial "
                   "Balance").format(m(kv.get("grni")))
        ),
        sign="&minus;" if flt(kv.get("stock_adj")) < 0 else "+",
        adj=m(abs(flt(kv.get("stock_adj")))), cl=m(kv.get("closing")),
        cogs=m(kv.get("formula_cogs")), ccy=kv.get("currency") or "",
    )


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

def _sb(co, fd, td, wh=None):
    p = {"company": co, "from_date": str(fd), "to_date": str(td)}
    if wh: p["warehouse"] = wh
    return _url("Stock Balance", p)


def _pse(co, fd, td, wh=None, ptype=None):
    """Purchase Stock Entries drill-down carrying the exact date filters and
    the Local/Import/Landed Cost/Returns classification of the clicked row."""
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    if ptype: p["purchase_type"] = ptype
    return _url("Purchase Stock Entries", p)

def _sr(co, fd, td):
    return _url("Sales Register", {"company": co, "from_date": fd, "to_date": td})

def _pi_drill(co, fd, td, wh=None, txn="All", ctype="All"):
    p = {"company": co, "from_date": fd, "to_date": td,
         "transaction": txn, "currency_type": ctype}
    if wh:
        p["warehouse"] = wh
    return _url("Purchase Invoice Stocked Items", p)

def _gl_account(co, fd, td, account):
    """General Ledger for one account, so a ledger figure can be opened where it lives."""
    return _url("General Ledger", {"company": co, "from_date": fd, "to_date": td,
                                   "account": account})


def _recon_drill(co, fd, td, head, wh=None, cc=None):
    """Reconciliation head drill-down: the documents making up the clicked bridging line."""
    p = {"company": co, "from_date": fd, "to_date": td, "head": head}
    if wh:
        p["warehouse"] = wh
    if cc:
        p["cost_center"] = cc
    return _url("Trading Reconciliation Detail", p)


def _lcv_drill(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh:
        p["warehouse"] = wh
    return _url("Landed Cost Voucher Drill", p)


def _pi_list(co, fd, td, company_cur, kind):
    """List-view drill-down: all Purchase Invoices behind a purchase row."""
    p = {
        "company": co,
        "posting_date": json.dumps(["between", [fd, td]]),
        "docstatus": 1,
    }
    has_epr = frappe.db.has_column("Purchase Invoice", "epromise_vr")
    if kind == "local":
        p["currency"] = company_cur
        p["is_return"] = 0
    elif kind == "import":
        p["is_return"] = 0
        if has_epr:                                  # migrated imports are BHD-posted, tagged IP
            p["epromise_vr"] = json.dumps(["like", "IP%"])
        else:
            p["currency"] = json.dumps(["!=", company_cur])
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
    r = _sle(co, wh,
             ["sle.posting_date<=%s"],
             [td],
             "COALESCE(SUM(sle.stock_value_difference),0) AS v")
    return flt(r[0].v) if r else 0.0


def purchase_split(co, fd, td, wh=None, cc_vnos=None):
    """
    Purchase breakdown per the COGS Reconciliation document logic.

    Source for local_pur / import_pur / pur_ret:
        ALL submitted Purchase Invoices (with AND without update_stock),
        stocked items only (is_stock_item=1), base_net_amount (VAT excluded),
        split local / import by pi.currency vs company default currency.

    Source for lcv:
        Stock Ledger Entries with voucher_type='Landed Cost Voucher',
        for stocked items — always SLE-based because LCV always updates stock.

    Formula COGS = Opening + local_pur + import_pur + lcv - pur_ret - Closing
    If Difference (Formula COGS - GL COGS) != 0, it flags PI-without-update-stock
    or other posting gaps.
    """
    company_cur = frappe.db.get_value("Company", co, "default_currency") or ""

    # ── Warehouse clause for PI items ─────────────────────────────────────────
    wh_clause = "AND pii.warehouse = %s" if wh else ""
    wh_param  = [wh] if wh else []

    vno_pi = ""
    vp_pi  = []
    if cc_vnos is not None:
        if cc_vnos:
            ph     = ",".join(["%s"] * len(cc_vnos))
            vno_pi = f"AND pi.name IN ({ph})"
            vp_pi  = list(cc_vnos)
        else:
            vno_pi = "AND 1=0"

    # Import classification: foreign currency OR a migrated import voucher.
    # Migration posts imports in company currency (BHD) so the currency test alone misses
    # them; they are tagged epromise_vr='IP|<vr>'. Guard the column so other sites are unaffected.
    ip_expr = ""
    if frappe.db.has_column("Purchase Invoice", "epromise_vr"):
        ip_expr = "OR pi.epromise_vr LIKE 'IP%%'"

    # ALL PI (with + without update_stock), stocked items, split local vs import
    pi_rows = frappe.db.sql(f"""
        SELECT
            CASE WHEN COALESCE(pi.currency, %s) <> %s {ip_expr} THEN 1 ELSE 0 END       AS is_imp,
            COALESCE(SUM(CASE WHEN pi.is_return=0 THEN pii.base_net_amount ELSE 0 END), 0) AS gross,
            COALESCE(ABS(SUM(CASE WHEN pi.is_return=1 THEN pii.base_net_amount ELSE 0 END)), 0) AS ret
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi  ON pi.name = pii.parent
        INNER JOIN `tabItem`             itm ON itm.name = pii.item_code
        WHERE pi.company = %s
          AND pi.posting_date BETWEEN %s AND %s
          AND pi.docstatus = 1
          AND itm.is_stock_item = 1
          {wh_clause} {vno_pi}
        GROUP BY is_imp
    """, [company_cur, company_cur, co, fd, td] + wh_param + vp_pi, as_dict=True)

    local_pur = import_pur = pur_ret = 0.0
    for row in pi_rows:
        if row.is_imp:
            import_pur += flt(row.gross)
        else:
            local_pur  += flt(row.gross)
        pur_ret += flt(row.ret)

    # ── LCV: from LCV document taxes (not SLE) ───────────────────────────────
    # ERPNext updates the source PI's SLE valuation directly on LCV submit
    # rather than creating separate SLE with voucher_type='Landed Cost Voucher'.
    # Querying LCV.taxes gives the correct charged amount.
    # LCV charges cannot be scoped by warehouse (Landed Cost Item has no warehouse
    # field), so use the period total for the company.
    lcv_r = frappe.db.sql("""
        SELECT COALESCE(SUM(lcvt.amount), 0) AS v
        FROM `tabLanded Cost Voucher` lcv
        INNER JOIN `tabLanded Cost Taxes and Charges` lcvt ON lcvt.parent = lcv.name
        WHERE lcv.company = %s
          AND lcv.posting_date BETWEEN %s AND %s
          AND lcv.docstatus = 1
    """, [co, fd, td], as_dict=True)
    lcv = flt(lcv_r[0].v) if lcv_r else 0.0

    return local_pur, import_pur, lcv, pur_ret


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

    # Purchases: PI base_net_amount for stocked items (consistent with report formula)
    r_pi = frappe.db.sql("""
        SELECT
            COALESCE(SUM(CASE WHEN pi.is_return=0 THEN pii.base_net_amount ELSE 0 END), 0) AS gross,
            COALESCE(ABS(SUM(CASE WHEN pi.is_return=1 THEN pii.base_net_amount ELSE 0 END)), 0) AS ret
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi  ON pi.name = pii.parent
        INNER JOIN `tabItem`             itm ON itm.name = pii.item_code
        WHERE pi.company = %s
          AND pi.posting_date BETWEEN %s AND %s
          AND pi.docstatus = 1
          AND itm.is_stock_item = 1
          AND itm.item_group = %s
    """, [co, fd, td, ig], as_dict=True)
    pi_gross  = flt(r_pi[0].gross) if r_pi else 0.0
    pi_ret    = flt(r_pi[0].ret)   if r_pi else 0.0

    # LCV: from LCV document taxes for this item group
    lcv_res = frappe.db.sql("""
        SELECT COALESCE(SUM(lcvt.amount * lci.amount / NULLIF(lcv_total.total,0)), 0) AS v
        FROM `tabLanded Cost Voucher` lcv
        INNER JOIN `tabLanded Cost Taxes and Charges` lcvt ON lcvt.parent = lcv.name
        INNER JOIN `tabLanded Cost Item` lci ON lci.parent = lcv.name
        INNER JOIN `tabItem` itm ON itm.name = lci.item_code AND itm.item_group = %s
        INNER JOIN (
            SELECT parent, SUM(amount) AS total FROM `tabLanded Cost Item` GROUP BY parent
        ) lcv_total ON lcv_total.parent = lcv.name
        WHERE lcv.company = %s
          AND lcv.posting_date BETWEEN %s AND %s
          AND lcv.docstatus = 1
    """, [ig, co, fd, td], as_dict=True)
    lcv_v = flt(lcv_res[0].v) if lcv_res else 0.0
    net_pur_v = pi_gross + lcv_v - pi_ret

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

def _fmt(v):
    return "{:,.3f}".format(flt(v, 3))

def H(label):
    return R(f"── {label} {'─'*(50-len(label))}", bold=True, row_type="recon_header")


# ── Main trading account section ──────────────────────────────────────────────

def _stock_accounts_merged_into_cogs(co):
    """Is the company routing its stock postings into the Cost of Goods Sold account itself?

    Steel Force point Stock Received But Not Billed and Stock Adjustment at the COGS account so
    that Purchases means everything that increased stock value. When they do, the COGS account
    no longer holds only the cost of goods sold: a Purchase Receipt credits it, the supplier
    invoice debits it back, and stock adjustments land there too. The ledger figure the trading
    account reconciles to must then be the sales postings alone, or it is comparing the formula
    against a number that includes the purchase side twice over.
    """
    values = frappe.db.get_value(
        "Company", co, ["stock_received_but_not_billed", "stock_adjustment_account"], as_dict=True
    ) or {}

    merged = []
    for account in (values.get("stock_received_but_not_billed"), values.get("stock_adjustment_account")):
        if not account:
            continue
        if frappe.db.get_value("Account", account, "account_type") == "Cost of Goods Sold":
            merged.append(account)

    return merged


def _tb_cogs_full(co, fd, td, cc=None):
    """Full ledger (Trial Balance) COGS: net of ALL postings to COGS accounts, every voucher type."""
    p = {"company": co, "from_date": fd, "to_date": td}
    cc_cond = " AND gle.cost_center=%(cost_center)s" if cc else ""
    if cc: p["cost_center"] = cc
    r = frappe.db.sql("SELECT COALESCE(SUM(gle.debit-gle.credit),0) v "
        "FROM `tabGL Entry` gle INNER JOIN `tabAccount` acc ON acc.name=gle.account "
        "WHERE gle.company=%(company)s AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s "
        "AND gle.is_cancelled=0 AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold'" + cc_cond,
        p, as_dict=True)
    return flt(r[0].v) if r else 0.0


def _sales_stock_out(co, fd, td, wh=None, cc=None):
    """Positive stock value that left via SI/DN legs posting to COGS (= -sum SLE svd for those vouchers)."""
    r = frappe.db.sql("SELECT COALESCE(SUM(sle.stock_value_difference),0) v FROM `tabStock Ledger Entry` sle "
        "WHERE sle.company=%s AND sle.posting_date BETWEEN %s AND %s "
        "AND sle.voucher_type IN ('Sales Invoice','Delivery Note') "
        "AND sle.voucher_no IN (SELECT DISTINCT g.voucher_no FROM `tabGL Entry` g "
        "  INNER JOIN `tabAccount` a ON a.name=g.account "
        "  WHERE g.company=%s AND g.posting_date BETWEEN %s AND %s AND g.is_cancelled=0 "
        "  AND g.voucher_type IN ('Sales Invoice','Delivery Note') AND a.account_type='Cost of Goods Sold')",
        [co, fd, td, co, fd, td], as_dict=True)
    return -flt(r[0].v) if r else 0.0


def _srbnb_movement(co, fd, td):
    """Net movement on Stock Received But Not Billed accounts (informational)."""
    accts = frappe.db.get_all("Account", filters={"company": co,
        "account_type": "Stock Received But Not Billed"}, pluck="name")
    if not accts:
        return 0.0
    ph = ",".join(["%s"] * len(accts))
    r = frappe.db.sql("SELECT COALESCE(SUM(debit-credit),0) v FROM `tabGL Entry` "
        "WHERE company=%s AND account IN (" + ph + ") AND is_cancelled=0 "
        "AND posting_date BETWEEN %s AND %s", [co] + accts + [fd, td], as_dict=True)
    return flt(r[0].v) if r else 0.0


def _sle_svd_by_vt(co, fd, td):
    """Sum of Stock Ledger stock_value_difference grouped by voucher_type over the period."""
    rows = frappe.db.sql("SELECT voucher_type vt, COALESCE(SUM(stock_value_difference),0) v "
        "FROM `tabStock Ledger Entry` WHERE company=%s AND posting_date BETWEEN %s AND %s "
        "AND is_cancelled=0 GROUP BY voucher_type", [co, fd, td], as_dict=True)
    return {r.vt: flt(r.v) for r in rows}


def build_main(co, fd, td, wh, cc, merge_adj=0, received_basis=False):
    cc_vnos = get_cc_vouchers(co, cc) if cc else None
    op      = opening_stock(co, fd, wh)
    cl      = closing_stock(co, td, wh)
    recon   = stock_recon_adjustment(co, fd, td, wh)
    local_pur, import_pur, _lcv, pur_ret = purchase_split(co, fd, td, wh, cc_vnos)

    # Formula: COGS = Opening + Local (PI) + Import (PI) − Returns ± Stock Adjustments − Closing
    # LCV adjusts stock valuation directly (via SLE repost), so its effect
    # flows through the opening/closing stock difference automatically.
    #
    # "Stock Adjustments" is the trading formula's own term for every stock move that is neither a
    # purchase nor a sale. Stock Reconciliations were always counted here; Stock Entries (Material
    # Receipt, Material Issue, transfers that change value) used to sit below the line as a
    # reconciling item instead, which put the same money in a different place from the formula the
    # accountant is reading. They are counted here now, so the build-up matches the formula and the
    # bridge below is left with genuine timing and posting differences only.
    _svd         = _sle_svd_by_vt(co, fd, td)
    se_adj       = flt(_svd.get("Stock Entry", 0.0), 3)
    net_pur      = local_pur + import_pur - pur_ret
    # Goods received whose supplier invoice is not posted yet. They are already inside Closing
    # Stock, so the formula subtracts them; without this line it never adds them, and NET COGS
    # comes out short by exactly this much. Naming it here rather than below the NET COGS line is
    # what lets the report show ONE cost of goods sold instead of two figures and a bridge.
    # Goods received whose supplier invoice is not posted yet. They are inside Closing Stock, which
    # the formula subtracts, while the Purchases line cannot include them because no invoice exists.
    # The classic formula has no term for them, so they are shown under Reconciliation to Trial
    # Balance - the trading formula stays exactly Opening + Purchases +/- Adjustments - Closing, and
    # this is the timing item that carries it to the ledger figure.
    grni         = flt((_svd.get("Purchase Receipt", 0.0) + _svd.get("Purchase Invoice", 0.0)) - net_pur, 3)
    goods_avail  = op + net_pur
    stock_adj    = flt(recon + se_adj, 3)

    # ── Presentation switches ────────────────────────────────────────────────
    # The client's accountant asked why stock adjustments and goods-received-not-invoiced are
    # not simply posted to the Cost of Goods Sold account. They must not be — one is a separate
    # expense whose whole purpose is to keep write-downs visible, and the other is a liability
    # that Period Closing would sweep into retained earnings mid-accrual. What they actually
    # want is to READ one number, and that is a presentation question, so it is answered here
    # rather than in the chart of accounts.
    #
    #   merge_stock_adjustments — cosmetic only. Adjustments are already inside the formula, so
    #                             NET COGS does not move by a fil; the separate lines collapse
    #                             into one, with the drill-downs kept.
    #   cogs_basis = Goods Received — NOT cosmetic. It moves goods received but not yet invoiced
    #                             into Purchases, so COGS is stated on what arrived rather than
    #                             on what was invoiced. The figure changes by exactly that
    #                             amount, and the report says so on its face.
    pur_for_cogs = flt(net_pur + grni, 3) if received_basis else net_pur
    grni_in_recon = 0.0 if received_basis else grni

    formula_cogs = flt(op + pur_for_cogs, 3) + stock_adj - cl
    goods_avail  = flt(op + pur_for_cogs, 3)
    # Reconcile periodic Trading Formula COGS to the ledger (Trial Balance) COGS.
    merged_accounts = _stock_accounts_merged_into_cogs(co)
    # With the stock accounts merged into COGS the account balance is not the cost of goods
    # sold — it nets the purchase side in and out again. The sales postings are.
    tb_full_cogs = (
        gl_cogs_total(co, fd, td, cc) if merged_accounts else _tb_cogs_full(co, fd, td, cc)
    )
    _sales_gl    = gl_cogs_total(co, fd, td, cc)
    nonsales     = flt(tb_full_cogs - _sales_gl, 3)
    sales_drift  = flt(_sales_gl - _sales_stock_out(co, fd, td, wh, cc), 3)
    other_adj    = flt((tb_full_cogs - formula_cogs) - nonsales - sales_drift, 3)
    adj_recon    = flt(_svd.get("Stock Reconciliation", 0.0) - recon, 3)
    adj_round    = flt(other_adj - grni_in_recon - adj_recon, 3)
    g_sales, sal_ret, net_sales = sales_data(co, fd, td, cc)
    gross_profit = net_sales - formula_cogs
    opening_date = str(add_days(fd, -1))
    currency     = frappe.db.get_value("Company", co, "default_currency") or ""

    rows = [
        R("SALES", bold=True, row_type="section"),
        R("Gross Sales Revenue",          credit=g_sales,   indent=1, link=_sr(co, fd, td)),
        R("Less: Returns / Credit Notes", debit=sal_ret,    indent=1, link=_sr(co, fd, td)),
        R("NET SALES",                    credit=net_sales, bold=True, row_type="net_sales"),
        S(),

        R("COST OF GOODS SOLD", bold=True, row_type="section"),
        R("Opening Stock + Purchases ± Stock Adjustments − Closing Stock "
          "= Cost of Goods Sold", indent=1, row_type="note"),
        R("Opening Stock", debit=op, indent=1,
          link=_sb(co, opening_date, opening_date, wh)),

        # ── Purchases (ALL PI, with + without update_stock) ──────────────────
        R("Purchases", bold=True, indent=1),
    ]

    if local_pur:
        rows.append(R("Local Purchases  (PI — company currency)",
                      debit=local_pur, indent=2,
                      link=_pi_drill(co, fd, td, wh, txn="Purchases", ctype="Local")))
    if import_pur:
        rows.append(R("Import Purchases  (PI — foreign currency)",
                      debit=import_pur, indent=2,
                      link=_pi_drill(co, fd, td, wh, txn="Purchases", ctype="Import")))
    if pur_ret:
        rows.append(R("Less: Purchase Returns",
                      credit=pur_ret, indent=2,
                      link=_pi_drill(co, fd, td, wh, txn="Returns", ctype="All")))

    if received_basis and grni:
        rows.append(R("Add: Goods Received Not Yet Invoiced  (stated on receipts, not invoices)",
                      debit=grni, indent=2,
                      link=_recon_drill(co, fd, td, "Received vs Billed (SRBNB)", wh, cc)))

    rows.append(R("Net Purchases" + ("  (per goods received)" if received_basis else ""),
                  debit=pur_for_cogs, bold=True, indent=1, row_type="subtotal",
                  link=_pi_drill(co, fd, td, wh)))


    if merge_adj:
        # One line instead of two. NET COGS is untouched — these were always inside the
        # formula — so this only changes how much of the working the reader is shown.
        if stock_adj:
            rows.append(R("Stock Adjustments  (reconciliations and stock entries, combined)",
                          debit=(stock_adj if stock_adj > 0 else 0),
                          credit=(abs(stock_adj) if stock_adj < 0 else 0), indent=1,
                          link=_recon_drill(co, fd, td, "All", wh, cc)))
    elif recon:
        if recon > 0:
            rows.append(R("Stock Reconciliation  (Excess Found / Opening Load)",
                          debit=recon, indent=1, link=_sl(co, fd, td, wh)))
        else:
            rows.append(R("Stock Reconciliation  (Shortage / Write-off)",
                          credit=abs(recon), indent=1, link=_sl(co, fd, td, wh)))

    # A head worth nothing explains nothing: only lines with a value are printed, so the block
    # shows what actually stands between the two COGS figures instead of a column of zeros.
    if se_adj and not merge_adj:
        if se_adj > 0:
            rows.append(R("Stock Entries / Transfers  (received into stock, no purchase)",
                          debit=se_adj, indent=1,
                          link=_recon_drill(co, fd, td, "Stock Entries / Transfers", wh, cc)))
        else:
            rows.append(R("Stock Entries / Transfers  (issued out of stock, no sale)",
                          credit=abs(se_adj), indent=1,
                          link=_recon_drill(co, fd, td, "Stock Entries / Transfers", wh, cc)))

    recon_lines = [
        ("Add: Goods Received Not Yet Invoiced  (in Closing Stock, not in Purchases)", grni_in_recon,
         "Received vs Billed (SRBNB)"),
        ("Less: Sales valuation drift (SLE vs GL on sales)", sales_drift, "Sales valuation drift"),
        ("Add: Non-stock / Non-sales COGS postings", nonsales, "Non-stock / Non-sales COGS postings"),
        ("Stock Reconciliation value vs GL posting", adj_recon, "Stock Reconciliation vs GL"),
        ("Rounding (3-dp aggregation)", adj_round, None),
    ]

    rows += [
        R("Less: Closing Stock", credit=cl, indent=1, link=_sb(co, td, td, wh)),
        R("NET COGS  (Calculated — Trading Formula)",
          debit =formula_cogs if formula_cogs >= 0 else 0,
          credit=abs(formula_cogs) if formula_cogs <  0 else 0,
          bold=True, row_type="net_cogs"),
        R("%s + %s %s %s − %s = %s%s"
          % (_fmt(op), _fmt(pur_for_cogs), "−" if stock_adj < 0 else "+", _fmt(abs(stock_adj)),
             _fmt(cl), _fmt(formula_cogs),
             "   (Purchases stated per goods received — includes %s not yet invoiced)" % _fmt(grni)
             if received_basis else ""), indent=2, row_type="note"),
        *([
            R("Cost of Goods Sold also receives this company's purchase receipts and stock "
              "adjustments, so the ledger figure below counts the sales postings only.",
              indent=2, row_type="note"),
        ] if merged_accounts else []),
        R("Reconciliation to Trial Balance", bold=True, indent=1, row_type="section",
          link=_recon_drill(co, fd, td, "All", wh, cc)),
        *([
            R(label,
              debit=(value if value >= 0 else 0),
              credit=(abs(value) if value < 0 else 0), indent=2,
              link=_recon_drill(co, fd, td, head, wh, cc) if head else None)
            for label, value, head in recon_lines
            if abs(flt(value, 3)) > 0.0005
        ] or [
            # Positive assurance beats an empty heading: a reader who sees nothing under the
            # heading cannot tell whether the report agreed or simply failed to check.
            R("Agrees with the Trial Balance — nothing to reconcile", indent=2)
        ]),
        R("NET COGS  (Trial Balance)",
          debit=(tb_full_cogs if tb_full_cogs >= 0 else 0),
          credit=(abs(tb_full_cogs) if tb_full_cogs < 0 else 0),
          bold=True, row_type="net_cogs"),
        S(),
        R("GROSS PROFIT" if gross_profit >= 0 else "GROSS LOSS",
          debit =abs(gross_profit) if gross_profit <  0 else 0,
          credit=gross_profit       if gross_profit >= 0 else 0,
          bold=True, row_type="gross_profit"),
        S(),
    ]

    kv = {
        "opening":          op,
        # the header prints the figure the formula actually used, which on the received basis
        # is purchases plus the goods not yet invoiced
        "net_purchases":    pur_for_cogs,
        "received_basis":   received_basis,
        "closing":          cl,
        "formula_cogs":     formula_cogs,
        "stock_adj":        stock_adj,
        "grni":             grni,
        "net_sales":        net_sales,
        "gross_profit":     gross_profit,
        "gross_margin_pct": round(gross_profit / net_sales * 100, 1) if net_sales else 0.0,
        "currency":         currency,
    }
    return rows, kv


# ── Compact breakdown sections ────────────────────────────────────────────────

def build_warehouse_breakdown(co, fd, td, cc):
    warehouses = non_transit_warehouses(co)
    if len(warehouses) <= 1:
        return []

    rows = [S(), H("BREAKDOWN BY WAREHOUSE  (purchases per invoices; excludes goods not yet invoiced)")]
    for wh in warehouses:
        op   = opening_stock(co, fd, wh)
        cl   = closing_stock(co, td, wh)
        loc, imp, _lcv, pur_ret = purchase_split(co, fd, td, wh)
        net_pur = loc + imp - pur_ret
        cogs    = flt(op + net_pur - cl, 3)

        if op == 0 and net_pur == 0 and cl == 0:
            continue

        rows += [
            S(),
            R(wh, bold=True, indent=1, row_type="wh_header"),
            R("Opening Stock",      debit=op,      indent=2, link=_sb(co, str(add_days(fd, -1)), str(add_days(fd, -1)), wh)),
            R("Net Purchases",      debit=net_pur,  indent=2, link=_sl(co, fd, td, wh)),
            R("Closing Stock",      credit=cl,      indent=2, link=_sb(co, fd, td, wh)),
            R("NET COGS (Formula)", debit=cogs,     indent=2, bold=True, row_type="subtotal"),
        ]
    return rows


def build_item_group_breakdown(co, fd, td, wh, cc):
    groups = item_groups_with_activity(co, fd, td, wh)
    if not groups:
        return []

    rows = [S(), H("BREAKDOWN BY ITEM GROUP  (purchases per invoices; excludes goods not yet invoiced)")]
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
