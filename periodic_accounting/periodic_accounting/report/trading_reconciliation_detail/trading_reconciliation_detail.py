# periodic_accounting/periodic_accounting/report/trading_reconciliation_detail/trading_reconciliation_detail.py
"""Every line under "Reconciliation to Trial Balance", broken down to the documents behind it.

The Audit Trading Account Report proves NET COGS (Trading Formula) ties to NET COGS (Trial
Balance). It does not say which documents made up each bridging line, so a reviewer sees
"Sales valuation drift 25.738" with nowhere to go. This report answers that per head, with the
reason each document lands there.

Head totals come from the audit report's own helper functions rather than being recalculated, so
the two reports cannot drift apart. Where the listed documents do not add up to the head total,
the gap is shown as its own row instead of being quietly absorbed.
"""

import frappe
from frappe import _
from frappe.utils import flt

AUDIT = (
    "periodic_accounting.periodic_accounting.report"
    ".audit_trading_account_report.audit_trading_account_report"
)

HEADS = (
    "Sales valuation drift",
    "Non-stock / Non-sales COGS postings",
    "Received vs Billed (SRBNB)",
    "Stock Entries / Transfers",
    "Stock Reconciliation vs GL",
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    company = filters.get("company")
    from_date, to_date = filters.get("from_date"), filters.get("to_date")
    if not (company and from_date and to_date):
        frappe.throw(_("Company, From Date and To Date are required."))

    audit = frappe.get_module(AUDIT)
    wanted = filters.get("head")
    rows = []

    if not wanted or wanted in ("All", "Sales valuation drift"):
        rows += _sales_drift_block(audit, company, from_date, to_date, filters)
    if not wanted or wanted in ("All", "Non-stock / Non-sales COGS postings"):
        rows += _non_sales_block(audit, company, from_date, to_date, filters)
    if not wanted or wanted in ("All", "Received vs Billed (SRBNB)"):
        rows += _srbnb_block(audit, company, from_date, to_date, filters)
    if not wanted or wanted in ("All", "Stock Entries / Transfers"):
        rows += _stock_entry_block(audit, company, from_date, to_date, filters)
    if not wanted or wanted in ("All", "Stock Reconciliation vs GL"):
        rows += _stock_recon_block(audit, company, from_date, to_date, filters)

    return _columns(), rows


def _columns():
    return [
        {"label": _("Particulars"), "fieldname": "particulars", "fieldtype": "Data", "width": 300},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 120},
        {"label": _("Voucher"), "fieldname": "voucher", "fieldtype": "Dynamic Link",
         "options": "voucher_type", "width": 170},
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
        {"label": _("Ledger (GL)"), "fieldname": "gl_value", "fieldtype": "Currency", "width": 130},
        {"label": _("Stock (SLE)"), "fieldname": "stock_value", "fieldtype": "Currency", "width": 130},
        {"label": _("Difference"), "fieldname": "difference", "fieldtype": "Currency", "width": 120},
        {"label": _("Why it is here"), "fieldname": "reason", "fieldtype": "Data", "width": 420},
    ]


# ── row helpers ───────────────────────────────────────────────────────────────

def _head(label, total, explanation):
    return {"particulars": label, "difference": total, "reason": explanation,
            "is_group": 1, "indent": 0}


def _detail(particulars, voucher_type, voucher, posting_date, gl, stock, diff, reason):
    return {"particulars": particulars, "voucher_type": voucher_type, "voucher": voucher,
            "posting_date": posting_date, "gl_value": gl, "stock_value": stock,
            "difference": diff, "reason": reason, "indent": 1}


def _remainder(head_total, listed, note):
    """What the documents above do not account for. Shown, never hidden."""
    gap = flt(head_total - listed, 3)
    if abs(gap) <= 0.0005:
        return []
    return [{"particulars": _("Not explained by the documents above"), "difference": gap,
             "reason": note, "indent": 1}]


def _blank():
    return [{"particulars": "", "indent": 0}]


# ── head: sales valuation drift ───────────────────────────────────────────────

def _sales_drift_block(audit, co, fd, td, filters):
    wh = filters.get("warehouse")
    cc = filters.get("cost_center")
    total = flt(
        audit.gl_cogs_total(co, fd, td, cc) - audit._sales_stock_out(co, fd, td, wh, cc), 3
    )
    rows = [_head(
        _("Sales valuation drift  (GL COGS vs stock actually shipped)"), total,
        _("The ledger charged one cost to COGS while the Stock Ledger removed another for the "
          "same sales voucher. Almost always a Repost Item Valuation that has not finished, or "
          "was skipped: the two sides were written at different valuations."),
    )]

    detail = frappe.db.sql(
        """
        SELECT v.voucher_type, v.voucher_no, v.posting_date, v.gl_cogs, v.sle_out,
               ROUND(v.gl_cogs - v.sle_out, 3) AS drift
        FROM (
          SELECT g.voucher_type, g.voucher_no, g.posting_date,
                 ROUND(SUM(g.debit - g.credit), 3) AS gl_cogs,
                 ROUND(-COALESCE((SELECT SUM(s.stock_value_difference)
                     FROM `tabStock Ledger Entry` s
                     WHERE s.voucher_no = g.voucher_no AND s.voucher_type = g.voucher_type
                       AND s.is_cancelled = 0), 0), 3) AS sle_out
          FROM `tabGL Entry` g
          INNER JOIN `tabAccount` a ON a.name = g.account
          WHERE g.company = %(company)s
            AND g.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND g.is_cancelled = 0
            AND g.voucher_type IN ('Sales Invoice', 'Delivery Note')
            AND a.account_type = 'Cost of Goods Sold'
          GROUP BY g.voucher_type, g.voucher_no, g.posting_date
        ) v
        WHERE ABS(v.gl_cogs - v.sle_out) > 0.0005
        ORDER BY ABS(v.gl_cogs - v.sle_out) DESC
        """,
        {"company": co, "from_date": fd, "to_date": td},
        as_dict=True,
    )

    reposted = _vouchers_with_pending_repost(co)
    listed = 0.0
    for r in detail:
        listed += flt(r.drift)
        why = (
            _("GL is higher: the sale was costed above what the Stock Ledger later settled on")
            if flt(r.drift) > 0
            else _("Stock Ledger is higher: the ledger was costed below the value that left stock")
        )
        if r.voucher_no in reposted:
            why += _(" — a Repost Item Valuation for this voucher is still Queued or Failed")
        rows.append(_detail(r.voucher_no, r.voucher_type, r.voucher_no, r.posting_date,
                            flt(r.gl_cogs), flt(r.sle_out), flt(r.drift), why))

    rows += _remainder(total, listed,
        _("Vouchers outside the sales-COGS pairing above, e.g. a COGS posting on a sales voucher "
          "with no stock movement at all."))
    return rows + _blank()


def _vouchers_with_pending_repost(company):
    """Vouchers whose valuation repost has not completed — the usual cause of a GL/SLE gap."""
    rows = frappe.db.get_all(
        "Repost Item Valuation",
        filters={"company": company, "status": ["in", ["Queued", "In Progress", "Failed"]]},
        fields=["voucher_no"],
        limit=5000,
    )
    return {r.voucher_no for r in rows if r.voucher_no}


# ── head: non-stock / non-sales COGS postings ─────────────────────────────────

def _non_sales_block(audit, co, fd, td, filters):
    cc = filters.get("cost_center")
    total = flt(audit._tb_cogs_full(co, fd, td, cc) - audit.gl_cogs_total(co, fd, td, cc), 3)
    rows = [_head(
        _("Non-stock / Non-sales COGS postings"), total,
        _("Anything charged to a Cost of Goods Sold account by a voucher that is not a sale — "
          "journal entries, service costs, expense reclassifications. The trading formula cannot "
          "see these because no stock moved."),
    )]

    cc_cond = " AND gle.cost_center = %(cost_center)s" if cc else ""
    params = {"company": co, "from_date": fd, "to_date": td}
    if cc:
        params["cost_center"] = cc

    detail = frappe.db.sql(
        """
        SELECT gle.voucher_type, gle.voucher_no, gle.posting_date, gle.account,
               ROUND(SUM(gle.debit - gle.credit), 3) AS amount,
               MAX(COALESCE(gle.remarks, '')) AS remarks
        FROM `tabGL Entry` gle
        INNER JOIN `tabAccount` acc ON acc.name = gle.account
        WHERE gle.company = %(company)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND gle.is_cancelled = 0
          AND acc.root_type = 'Expense'
          AND acc.account_type = 'Cost of Goods Sold'
          AND gle.voucher_type NOT IN ('Sales Invoice', 'Delivery Note')
        """ + cc_cond + """
        GROUP BY gle.voucher_type, gle.voucher_no, gle.posting_date, gle.account
        HAVING ABS(SUM(gle.debit - gle.credit)) > 0.0005
        ORDER BY ABS(SUM(gle.debit - gle.credit)) DESC
        """,
        params,
        as_dict=True,
    )

    listed = 0.0
    for r in detail:
        listed += flt(r.amount)
        reason = _("%(vt)s posted straight to %(acct)s") % {"vt": _(r.voucher_type),
                                                           "acct": r.account}
        if r.remarks:
            reason += " — " + r.remarks[:120]
        rows.append(_detail(r.account, r.voucher_type, r.voucher_no, r.posting_date,
                            flt(r.amount), 0, flt(r.amount), reason))

    rows += _remainder(total, listed, _("Postings excluded by the cost-centre filter."))
    return rows + _blank()


# ── head: received but not billed ─────────────────────────────────────────────

def _srbnb_block(audit, co, fd, td, filters):
    wh = filters.get("warehouse")
    cc_vnos = audit.get_cc_vouchers(co, filters.get("cost_center")) if filters.get("cost_center") else None
    local_pur, import_pur, _lcv, pur_ret = audit.purchase_split(co, fd, td, wh, cc_vnos)
    net_pur = local_pur + import_pur - pur_ret
    svd = audit._sle_svd_by_vt(co, fd, td)
    total = flt((svd.get("Purchase Receipt", 0.0) + svd.get("Purchase Invoice", 0.0)) - net_pur, 3)

    rows = [_head(
        _("Received vs Billed  (SRBNB / PI-without-update-stock timing)"), total,
        _("Stock arrived in one period and the invoice landed in another. A Purchase Receipt "
          "raises stock value with no purchase in the formula yet; a Purchase Invoice without "
          "Update Stock bills a purchase whose stock arrived earlier."),
    )]

    detail = frappe.db.sql(
        """
        SELECT sle.voucher_type, sle.voucher_no, MIN(sle.posting_date) AS posting_date,
               ROUND(SUM(sle.stock_value_difference), 3) AS svd
        FROM `tabStock Ledger Entry` sle
        WHERE sle.company = %(company)s
          AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND sle.is_cancelled = 0
          AND sle.voucher_type IN ('Purchase Receipt', 'Purchase Invoice')
        GROUP BY sle.voucher_type, sle.voucher_no
        HAVING ABS(SUM(sle.stock_value_difference)) > 0.0005
        ORDER BY ABS(SUM(sle.stock_value_difference)) DESC
        LIMIT 300
        """,
        {"company": co, "from_date": fd, "to_date": td},
        as_dict=True,
    )

    billed = {}
    if detail:
        names = [r.voucher_no for r in detail if r.voucher_type == "Purchase Receipt"]
        if names:
            for row in frappe.db.get_all(
                "Purchase Invoice Item",
                filters={"purchase_receipt": ["in", names], "docstatus": 1},
                fields=["purchase_receipt", "parent"],
            ):
                billed.setdefault(row.purchase_receipt, set()).add(row.parent)

    for r in detail:
        if r.voucher_type == "Purchase Receipt":
            invoices = billed.get(r.voucher_no)
            reason = (
                _("Receipt billed by %s") % ", ".join(sorted(invoices))
                if invoices
                else _("Receipt not yet billed — stock is in, the purchase is not")
            )
        else:
            reason = _("Purchase Invoice carrying its own stock movement")
        rows.append(_detail(r.voucher_no, r.voucher_type, r.voucher_no, r.posting_date,
                            0, flt(r.svd), flt(r.svd), reason))

    rows.append({"particulars": _("Less: purchases already in the trading formula"),
                 "difference": -flt(net_pur, 3), "indent": 1,
                 "reason": _("Net Purchases as the formula counted them, removed so only the "
                             "timing difference remains")})
    return rows + _blank()


# ── head: stock entries and transfers ─────────────────────────────────────────

def _stock_entry_block(audit, co, fd, td, filters):
    svd = audit._sle_svd_by_vt(co, fd, td)
    total = flt(svd.get("Stock Entry", 0.0), 3)
    rows = [_head(
        _("Stock Entries / Transfers  (non-purchase, non-sale)"), total,
        _("Stock value that moved without a purchase or a sale. A pure transfer nets to zero "
          "because value leaves one warehouse and enters another; anything left is one-sided — "
          "a Material Receipt, an Issue, a Repack, or a transfer booked at different rates."),
    )]

    detail = frappe.db.sql(
        """
        SELECT sle.voucher_no, se.purpose, se.posting_date, se.owner,
               ROUND(SUM(sle.stock_value_difference), 3) AS svd
        FROM `tabStock Ledger Entry` sle
        INNER JOIN `tabStock Entry` se ON se.name = sle.voucher_no
        WHERE sle.company = %(company)s
          AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND sle.is_cancelled = 0
          AND sle.voucher_type = 'Stock Entry'
        GROUP BY sle.voucher_no, se.purpose, se.posting_date, se.owner
        HAVING ABS(SUM(sle.stock_value_difference)) > 0.0005
        ORDER BY ABS(SUM(sle.stock_value_difference)) DESC
        """,
        {"company": co, "from_date": fd, "to_date": td},
        as_dict=True,
    )

    purpose_reason = {
        "Material Receipt": _("Stock introduced with no purchase document, so the formula never "
                              "saw a purchase for it"),
        "Material Issue": _("Stock written out with no sale, so the formula never saw it leave"),
        "Repack": _("Repack: consumed and produced values differ"),
        "Manufacture": _("Manufacture: consumed and produced values differ"),
        "Material Transfer": _("Transfer that did not net to zero — the value in differs from the "
                               "value out, usually a rate difference or in-transit leg"),
        "Send to Subcontractor": _("Sent to subcontractor"),
    }

    listed = 0.0
    for r in detail:
        listed += flt(r.svd)
        reason = purpose_reason.get(r.purpose, _("Purpose: %s") % r.purpose)
        if r.owner:
            reason += _(" — raised by %s") % r.owner
        rows.append(_detail(r.voucher_no, "Stock Entry", r.voucher_no, r.posting_date,
                            0, flt(r.svd), flt(r.svd), reason))

    rows += _remainder(total, listed, _("Entries netting to zero individually."))
    return rows + _blank()


# ── head: stock reconciliation vs GL ──────────────────────────────────────────

def _stock_recon_block(audit, co, fd, td, filters):
    wh = filters.get("warehouse")
    recon = audit.stock_recon_adjustment(co, fd, td, wh)
    svd = audit._sle_svd_by_vt(co, fd, td)
    total = flt(svd.get("Stock Reconciliation", 0.0) - recon, 3)
    rows = [_head(
        _("Stock Reconciliation value vs GL posting"), total,
        _("Where a Stock Reconciliation's ledger effect differs from the adjustment the formula "
          "took, typically because the reconciliation sits outside the warehouse filter."),
    )]

    detail = frappe.db.sql(
        """
        SELECT sle.voucher_no, MIN(sle.posting_date) AS posting_date,
               ROUND(SUM(sle.stock_value_difference), 3) AS svd,
               GROUP_CONCAT(DISTINCT sle.warehouse) AS warehouses
        FROM `tabStock Ledger Entry` sle
        WHERE sle.company = %(company)s
          AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND sle.is_cancelled = 0
          AND sle.voucher_type = 'Stock Reconciliation'
        GROUP BY sle.voucher_no
        HAVING ABS(SUM(sle.stock_value_difference)) > 0.0005
        ORDER BY ABS(SUM(sle.stock_value_difference)) DESC
        """,
        {"company": co, "from_date": fd, "to_date": td},
        as_dict=True,
    )

    for r in detail:
        rows.append(_detail(r.voucher_no, "Stock Reconciliation", r.voucher_no, r.posting_date,
                            0, flt(r.svd), flt(r.svd),
                            _("Warehouses: %s") % (r.warehouses or "")))

    rows.append({"particulars": _("Less: reconciliation already in the trading formula"),
                 "difference": -flt(recon, 3), "indent": 1,
                 "reason": _("The adjustment the formula already took, removed so only the "
                             "difference remains")})
    return rows + _blank()
