"""
Item COGS Analysis Report — Perpetual Inventory

Tabular, one row per item.  Key audit check: Variance column must be zero for every item.
  Variance = Opening + Inflows − Outflows − Closing
If non-zero → cancelled / unbalanced transaction needs investigation.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, today
from urllib.parse import urlencode


def _url(report, params):
    return f"/app/query-report/{report.replace(' ', '%20')}?{urlencode(params)}"


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data    = get_data(filters)
    chart   = _make_chart(data)
    summary = _make_summary(data)
    return columns, data, None, chart, summary


def get_columns():
    C = {"fieldtype": "Currency", "width": 120}
    return [
        {"label": _("Item"),       "fieldname": "item_code",  "fieldtype": "Link",
         "options": "Item",        "width": 130},
        {"label": _("Item Name"),  "fieldname": "item_name",  "fieldtype": "Data",    "width": 190},
        {"label": _("Group"),      "fieldname": "item_group", "fieldtype": "Link",
         "options": "Item Group",  "width": 120},
        {**C, "label": _("Opening"),          "fieldname": "opening"},
        {**C, "label": _("Local PR"),         "fieldname": "local_pr"},
        {**C, "label": _("Import PR"),        "fieldname": "import_pr"},
        {**C, "label": _("LCV"),              "fieldname": "lcv"},
        {**C, "label": _("PI Rate Adj"),      "fieldname": "pi_adj"},
        {**C, "label": _("Pur Returns"),      "fieldname": "pur_ret"},
        {**C, "label": _("Transfer In"),      "fieldname": "t_in"},
        {**C, "label": _("Transfer Out"),     "fieldname": "t_out"},
        {**C, "label": _("Mfg / Issue Out"),  "fieldname": "mfg_out"},
        {**C, "label": _("Sales COGS"),       "fieldname": "sales_cogs"},
        {**C, "label": _("Sales Ret In"),     "fieldname": "sales_ret_in"},
        {**C, "label": _("Closing"),          "fieldname": "closing"},
        {**C, "label": _("Variance ✓"),       "fieldname": "variance",
         "width": 130,
         "description": "Opening + Inflows − Outflows − Closing; must be 0"},
        {**C, "label": _("GL COGS"),          "fieldname": "gl_cogs"},
        {**C, "label": _("COGS Diff"),        "fieldname": "cogs_diff",
         "width": 130,
         "description": "Sales COGS (SLE) − GL COGS; must be 0 in perpetual"},
    ]


# ── Warehouse base ────────────────────────────────────────────────────────────

def _wh(co, wh):
    if wh:
        return "", ["sle.company=%s","sle.warehouse=%s","sle.is_cancelled=0"], [co, wh]
    return (
        "INNER JOIN `tabWarehouse` w ON w.name=sle.warehouse",
        ["w.company=%s","w.disabled=0",
         "(w.warehouse_type IS NULL OR w.warehouse_type!='Transit')",
         "sle.is_cancelled=0"],
        [co],
    )


# ── One big query: all movement categories per item in one shot ───────────────

def get_all_movements(co, fd, td, wh, ig, item, cc_vnos):
    """
    Returns list of dicts with item_code + all SLE movement buckets.
    Uses LEFT JOINs to PR/PI/SE tables to categorise each SLE row,
    avoiding per-item round-trips.
    """
    j, c, p = _wh(co, wh)
    base_where = " AND ".join(c)

    ig_cond   = " AND itm.item_group=%s"   if ig   else ""
    item_cond = " AND sle.item_code=%s"    if item else ""
    ig_p      = [ig]   if ig   else []
    item_p    = [item] if item else []

    vno_cond, vno_p = "", []
    if cc_vnos is not None:
        if not cc_vnos:
            return []
        ph = ",".join(["%s"]*len(cc_vnos))
        vno_cond = f" AND sle.voucher_no IN ({ph})"
        vno_p    = list(cc_vnos)

    company_cur = frappe.db.get_value("Company", co, "default_currency") or ""

    # IMPORTANT: MySQL binds %s in strict text order (SELECT before WHERE).
    # All CASE WHEN params (23) must come BEFORE the WHERE clause params.
    select_params = (
        [fd]                    # opening < fd
        + [fd, td, company_cur] # local_pr BETWEEN + currency =
        + [fd, td, company_cur] # import_pr BETWEEN + currency !=
        + [fd, td]              # lcv BETWEEN
        + [fd, td]              # pi_adj BETWEEN
        + [fd, td]              # pur_ret BETWEEN
        + [fd, td]              # t_in BETWEEN
        + [fd, td]              # t_out BETWEEN
        + [fd, td]              # mfg_out BETWEEN
        + [fd, td]              # sales_cogs BETWEEN
        + [fd, td]              # sales_ret_in BETWEEN
    )
    where_params = p + [td] + ig_p + item_p + vno_p   # company, posting_date<=td, optional filters

    rows = frappe.db.sql(f"""
        SELECT
            sle.item_code,
            itm.item_name,
            itm.item_group,

            /* Opening (before period) */
            COALESCE(SUM(CASE WHEN sle.posting_date < %s
                THEN sle.stock_value_difference ELSE 0 END), 0) AS opening,

            /* Local PR — non-return, company currency, positive svd */
            COALESCE(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type='Purchase Receipt'
                 AND COALESCE(pr.is_return,0)=0
                 AND sle.stock_value_difference>0
                 AND COALESCE(pr.currency,'')=%s
                THEN sle.stock_value_difference ELSE 0 END), 0) AS local_pr,

            /* Import PR — non-return, foreign currency, positive svd */
            COALESCE(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type='Purchase Receipt'
                 AND COALESCE(pr.is_return,0)=0
                 AND sle.stock_value_difference>0
                 AND COALESCE(pr.currency,'')!=%s
                THEN sle.stock_value_difference ELSE 0 END), 0) AS import_pr,

            /* Landed Cost Voucher */
            COALESCE(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type='Landed Cost Voucher'
                THEN sle.stock_value_difference ELSE 0 END), 0) AS lcv,

            /* PI rate adjustment (net; non-return PI) */
            COALESCE(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type='Purchase Invoice'
                 AND COALESCE(pi.is_return,0)=0
                THEN sle.stock_value_difference ELSE 0 END), 0) AS pi_adj,

            /* Purchase returns (PR return or PI return) */
            COALESCE(ABS(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.stock_value_difference<0
                 AND ((sle.voucher_type='Purchase Receipt' AND COALESCE(pr.is_return,0)=1)
                      OR (sle.voucher_type='Purchase Invoice' AND COALESCE(pi.is_return,0)=1))
                THEN sle.stock_value_difference ELSE 0 END)), 0) AS pur_ret,

            /* Transfer In — Material Transfer Stock Entry, positive svd */
            COALESCE(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type='Stock Entry'
                 AND COALESCE(se.purpose,'')='Material Transfer'
                 AND sle.stock_value_difference>0
                THEN sle.stock_value_difference ELSE 0 END), 0) AS t_in,

            /* Transfer Out — Material Transfer Stock Entry, negative svd */
            COALESCE(ABS(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type='Stock Entry'
                 AND COALESCE(se.purpose,'')='Material Transfer'
                 AND sle.stock_value_difference<0
                THEN sle.stock_value_difference ELSE 0 END)), 0) AS t_out,

            /* Mfg / Material Issue / Write-off — non-transfer SE + WO, negative svd */
            COALESCE(ABS(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.stock_value_difference<0
                 AND ((sle.voucher_type='Stock Entry'
                       AND COALESCE(se.purpose,'') NOT IN ('Material Transfer'))
                      OR sle.voucher_type='Work Order')
                THEN sle.stock_value_difference ELSE 0 END)), 0) AS mfg_out,

            /* Sales COGS — SI/DN outflows */
            COALESCE(ABS(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type IN ('Sales Invoice','Delivery Note')
                 AND sle.stock_value_difference<0
                THEN sle.stock_value_difference ELSE 0 END)), 0) AS sales_cogs,

            /* Sales Return — SI/DN inflows */
            COALESCE(SUM(CASE
                WHEN sle.posting_date BETWEEN %s AND %s
                 AND sle.voucher_type IN ('Sales Invoice','Delivery Note')
                 AND sle.stock_value_difference>0
                THEN sle.stock_value_difference ELSE 0 END), 0) AS sales_ret_in

        FROM `tabStock Ledger Entry` sle
        {j}
        INNER JOIN `tabItem` itm ON itm.name=sle.item_code
        LEFT JOIN `tabPurchase Receipt` pr
            ON pr.name=sle.voucher_no AND sle.voucher_type='Purchase Receipt'
        LEFT JOIN `tabPurchase Invoice` pi
            ON pi.name=sle.voucher_no AND sle.voucher_type='Purchase Invoice'
        LEFT JOIN `tabStock Entry` se
            ON se.name=sle.voucher_no AND sle.voucher_type='Stock Entry'

        WHERE {base_where}
          AND sle.posting_date <= %s
          {ig_cond} {item_cond} {vno_cond}

        GROUP BY sle.item_code, itm.item_name, itm.item_group
        ORDER BY itm.item_group, sle.item_code
    """,
    select_params + where_params,
    as_dict=True,
    )
    return rows


def get_closing_by_item(co, td, wh, ig, item):
    """Closing stock per item from Bin (live) or SLE cumulative (historical)."""
    ig_cond   = " AND itm.item_group=%s" if ig   else ""
    item_cond = " AND b.item_code=%s"    if item else ""
    ig_p      = [ig]   if ig   else []
    item_p    = [item] if item else []

    if getdate(td) >= getdate(today()):
        if wh:
            r = frappe.db.sql(f"""
                SELECT b.item_code, COALESCE(SUM(b.actual_qty*b.valuation_rate),0) AS v
                FROM `tabBin` b
                INNER JOIN `tabItem` itm ON itm.name=b.item_code
                WHERE b.warehouse=%s {ig_cond} {item_cond}
                GROUP BY b.item_code
            """, [wh]+ig_p+item_p, as_dict=True)
        else:
            r = frappe.db.sql(f"""
                SELECT b.item_code, COALESCE(SUM(b.actual_qty*b.valuation_rate),0) AS v
                FROM `tabBin` b
                INNER JOIN `tabWarehouse` w ON w.name=b.warehouse
                INNER JOIN `tabItem` itm ON itm.name=b.item_code
                WHERE w.company=%s AND w.disabled=0
                  AND (w.warehouse_type IS NULL OR w.warehouse_type!='Transit')
                  {ig_cond} {item_cond}
                GROUP BY b.item_code
            """, [co]+ig_p+item_p, as_dict=True)
    else:
        j, c, p = _wh(co, wh)
        base = " AND ".join(c)
        r = frappe.db.sql(f"""
            SELECT sle.item_code, COALESCE(SUM(sle.stock_value_difference),0) AS v
            FROM `tabStock Ledger Entry` sle {j}
            INNER JOIN `tabItem` itm ON itm.name=sle.item_code
            WHERE {base} AND sle.posting_date<=%s {ig_cond} {item_cond}
            GROUP BY sle.item_code
        """, p+[td]+ig_p+item_p, as_dict=True)
    return {row.item_code: flt(row.v) for row in r}


def get_gl_cogs_by_item(co, fd, td, cc):
    """GL COGS per item from perpetual auto-entries.

    ERPNext sets voucher_detail_no on COGS GL entries to the Stock Ledger Entry
    name (not the SI/DN item row name), so we resolve item_code via SLE.
    """
    p = {"company": co, "from_date": fd, "to_date": td}
    cc_cond = " AND gle.cost_center=%(cost_center)s" if cc else ""
    if cc: p["cost_center"] = cc
    r = frappe.db.sql(f"""
        SELECT
            sle.item_code AS item_code,
            COALESCE(SUM(gle.debit-gle.credit),0) AS v
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` acc ON acc.name=gle.account
        LEFT JOIN `tabStock Ledger Entry` sle ON sle.name=gle.voucher_detail_no
        WHERE gle.company=%(company)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND gle.voucher_type IN ('Sales Invoice','Delivery Note')
          AND gle.is_cancelled=0
          AND acc.root_type='Expense' AND acc.account_type='Cost of Goods Sold'
          {cc_cond}
        GROUP BY sle.item_code
    """, p, as_dict=True)
    return {row.item_code: flt(row.v) for row in r if row.item_code}


def get_cc_vouchers(co, cc):
    rows = frappe.db.sql(
        "SELECT DISTINCT voucher_no FROM `tabGL Entry` WHERE company=%s AND cost_center=%s AND is_cancelled=0",
        (co, cc), as_list=True,
    )
    return [x[0] for x in rows]


# ── Main ──────────────────────────────────────────────────────────────────────

def get_data(filters):
    co   = filters.company
    fd   = filters.get("from_date")
    td   = filters.get("to_date")

    if not co or not fd or not td:
        return []

    fd = str(fd)
    td = str(td)
    wh   = filters.get("warehouse")
    cc   = filters.get("cost_center")
    ig   = filters.get("item_group")
    item = filters.get("item")
    hide_zero = filters.get("hide_zero_variance")

    cc_vnos = get_cc_vouchers(co, cc) if cc else None

    movements    = get_all_movements(co, fd, td, wh, ig, item, cc_vnos)
    closing_map  = get_closing_by_item(co, td, wh, ig, item)
    gl_cogs_map  = get_gl_cogs_by_item(co, fd, td, cc)

    rows   = []
    totals = {k: 0.0 for k in (
        "opening","local_pr","import_pr","lcv","pi_adj","pur_ret",
        "t_in","t_out","mfg_out","sales_cogs","sales_ret_in",
        "closing","variance","gl_cogs","cogs_diff",
    )}

    for m in movements:
        code = m.item_code
        op       = flt(m.opening,       3)
        local_pr = flt(m.local_pr,      3)
        imp_pr   = flt(m.import_pr,     3)
        lcv_v    = flt(m.lcv,           3)
        pi_adj   = flt(m.pi_adj,        3)
        pur_ret  = flt(m.pur_ret,       3)
        t_in     = flt(m.t_in,          3)
        t_out    = flt(m.t_out,         3)
        mfg_out  = flt(m.mfg_out,       3)
        sales    = flt(m.sales_cogs,    3)
        s_ret    = flt(m.sales_ret_in,  3)
        cl       = flt(closing_map.get(code, 0), 3)
        gl_cogs  = flt(gl_cogs_map.get(code, 0), 3)

        total_in  = local_pr + imp_pr + lcv_v + pi_adj + s_ret + t_in
        total_out = pur_ret  + sales  + t_out + mfg_out
        variance  = flt(op + total_in - total_out - cl, 3)
        cogs_diff = flt(sales - gl_cogs, 3)

        # Skip rows with no activity if "hide zero variance" is on
        if hide_zero and variance == 0 and op == 0 and cl == 0 and sales == 0:
            continue

        sle_params = {"company": co, "from_date": fd, "to_date": td, "item_code": code}
        if wh: sle_params["warehouse"] = wh

        row = {
            "item_code":     code,
            "item_name":     m.item_name or code,
            "item_group":    m.item_group or "",
            "opening":       op,
            "local_pr":      local_pr,
            "import_pr":     imp_pr,
            "lcv":           lcv_v,
            "pi_adj":        pi_adj,
            "pur_ret":       pur_ret,
            "t_in":          t_in,
            "t_out":         t_out,
            "mfg_out":       mfg_out,
            "sales_cogs":    sales,
            "sales_ret_in":  s_ret,
            "closing":       cl,
            "variance":      variance,
            "gl_cogs":       gl_cogs,
            "cogs_diff":     cogs_diff,
            "_sle_link":     _url("Stock Ledger", sle_params),
            "_gl_link":      _url("General Ledger", {"company": co, "from_date": fd, "to_date": td}),
        }
        rows.append(row)

        for k in totals:
            totals[k] = flt(totals[k] + flt(row.get(k, 0)), 3)

    if not rows:
        return []

    rows.append({
        "item_code":  None,
        "item_name":  "TOTAL",
        "item_group": "",
        "bold":       True,
        "_row_type":  "total",
        **totals,
    })

    return rows


# ── Chart and summary ─────────────────────────────────────────────────────────

def _make_chart(data):
    item_rows = [r for r in data if r.get("item_code")]
    if not item_rows:
        return None

    top = sorted(item_rows, key=lambda r: r.get("sales_cogs", 0), reverse=True)[:12]
    labels     = [r["item_code"] for r in top]
    cogs_vals  = [flt(r.get("sales_cogs", 0), 2) for r in top]
    pur_vals   = [flt(r.get("local_pr", 0) + r.get("import_pr", 0) + r.get("lcv", 0) + r.get("pi_adj", 0), 2) for r in top]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Sales COGS",     "values": cogs_vals},
                {"name": "Net Purchases",  "values": pur_vals},
            ],
        },
        "type": "bar",
        "colors": ["#e53935", "#1e88e5"],
        "fieldtype": "Currency",
        "barOptions": {"spaceRatio": 0.3},
    }


def _make_summary(data):
    item_rows = [r for r in data if r.get("item_code")]
    if not item_rows:
        return []

    total_items    = len(item_rows)
    variance_items = sum(1 for r in item_rows if abs(flt(r.get("variance", 0))) > 0.005)
    total_cogs     = flt(sum(r.get("sales_cogs", 0) for r in item_rows), 2)
    total_diff     = flt(sum(r.get("cogs_diff",  0) for r in item_rows), 2)

    return [
        {"value": total_items,    "label": "Items Analyzed",        "indicator": "Blue"},
        {"value": variance_items, "label": "Items with Variance",
         "indicator": "Red" if variance_items else "Green"},
        {"value": total_cogs,     "label": "Total COGS (SLE)",      "datatype": "Currency",
         "indicator": "Orange"},
        {"value": total_diff,     "label": "SLE vs GL Difference",  "datatype": "Currency",
         "indicator": "Red" if abs(total_diff) > 0.005 else "Green"},
    ]
