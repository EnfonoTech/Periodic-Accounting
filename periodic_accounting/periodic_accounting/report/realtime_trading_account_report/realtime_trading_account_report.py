"""
Realtime Trading Account Report
─────────────────────────────────
Tally-style two-column (Dr | Cr) Trading Account.
Opening and closing stock are derived from SLE date-wise.
Purchases are split into Local / Import via GL account classification.
"""
import frappe
from frappe import _
from frappe.utils import flt, add_days
from urllib.parse import urlencode

from periodic_accounting.periodic_accounting.report.report_utils import (
    get_opening_stock,
    get_closing_stock,
    get_gl_purchase_split,
    get_stock_adjustments,
    get_sales,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data    = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"label": _("Particulars"),  "fieldname": "particulars", "fieldtype": "Data",     "width": 340},
        {"label": _("Amount (Dr)"),  "fieldname": "debit",       "fieldtype": "Currency",  "width": 180},
        {"label": _("Amount (Cr)"),  "fieldname": "credit",      "fieldtype": "Currency",  "width": 180},
    ]


# ── URL helpers ────────────────────────────────────────────────────────────────

def _url(report, params):
    return f"/app/query-report/{report.replace(' ', '%20')}?{urlencode(params)}"

def _sales_register(co, fd, td):
    return _url("Sales Register", {"company": co, "from_date": fd, "to_date": td})

def _purchase_entries(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Purchase Stock Entries", p)

def _sales_stock_entries(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Sales Stock Entries", p)

def _stock_adj(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Stock Ledger", p)

def _stock_balance(co, sb_fd, sb_td, wh=None):
    p = {"company": co, "from_date": str(sb_fd), "to_date": str(sb_td)}
    if wh: p["warehouse"] = wh
    return _url("Stock Balance", p)


# ── Main data builder ──────────────────────────────────────────────────────────

def get_data(filters):
    co = filters.get("company")
    fd = str(filters.get("from_date") or "")
    td = str(filters.get("to_date") or "")
    if not (co and fd and td):
        return []

    wh           = filters.get("warehouse")
    opening_date = str(add_days(fd, -1))

    opening_stock                         = get_opening_stock(filters)
    closing_stock                         = get_closing_stock(filters)
    pur                                   = get_gl_purchase_split(filters)
    stock_adjustments                     = get_stock_adjustments(filters)
    gross_sales, sal_returns, net_sales   = get_sales(filters)

    # Net Purchases = Local + Import + Landing Costs - Returns
    net_purchases   = pur.local_pur + pur.import_pur + pur.local_lc + pur.import_lc - pur.returns
    goods_available = opening_stock + net_purchases + stock_adjustments
    cogs            = goods_available - closing_stock
    gross_profit    = net_sales - cogs

    # Dr/Cr totals — both sides of the Trading Account always balance
    dr_total = goods_available + (gross_profit if gross_profit > 0 else 0)
    cr_total = net_sales + closing_stock + (abs(gross_profit) if gross_profit < 0 else 0)

    def R(particulars, debit=0, credit=0, bold=False, indent=0, link=None):
        return {
            "particulars": particulars,
            "debit":       flt(debit,  3),
            "credit":      flt(credit, 3),
            "bold":        bold,
            "indent":      indent,
            "link":        link,
        }

    def spacer():
        return {"particulars": "", "debit": 0, "credit": 0}

    gm_pct = round(gross_profit / net_sales * 100, 1) if net_sales else 0.0

    rows = [
        # ── SALES (Cr side) ────────────────────────────────────────────────────
        R("SALES  ← GL (Sales Invoice / Delivery Note)", bold=True),
        R("Gross Sales Revenue",
          credit=gross_sales, indent=1, link=_sales_register(co, fd, td)),
        R("Less: Sales Returns",
          debit=sal_returns,  indent=1, link=_sales_register(co, fd, td)),
        R("Net Sales Revenue",
          credit=net_sales, bold=True),
        spacer(),

        # ── COST OF GOODS SOLD (Dr side) ───────────────────────────────────────
        R("COST OF GOODS SOLD  ← SLE + GL", bold=True),
        R("Opening Stock",
          debit=opening_stock, indent=1,
          link=_stock_balance(co, opening_date, opening_date, wh)),
    ]

    # ── Purchases breakdown ────────────────────────────────────────────────────
    rows.append(R("Purchases  ← GL", bold=True, indent=1))
    if pur.local_pur:
        rows.append(R("Local Purchases",
                      debit=pur.local_pur, indent=2,
                      link=_purchase_entries(co, fd, td, wh)))
    if pur.import_pur:
        rows.append(R("Import Purchases",
                      debit=pur.import_pur, indent=2,
                      link=_purchase_entries(co, fd, td, wh)))
    if pur.import_lc:
        rows.append(R("Import Landing Cost",
                      debit=pur.import_lc, indent=2,
                      link=_purchase_entries(co, fd, td, wh)))
    if pur.local_lc:
        rows.append(R("Local Landing Cost",
                      debit=pur.local_lc, indent=2,
                      link=_purchase_entries(co, fd, td, wh)))
    if pur.returns:
        rows.append(R("Less: Purchase Returns",
                      credit=pur.returns, indent=2,
                      link=_purchase_entries(co, fd, td, wh)))

    rows.append(R("Net Purchases", debit=net_purchases, bold=True, indent=1))

    if stock_adjustments != 0:
        rows.append(R(
            "+/- Stock Adjustments  (Stock Entry / Reconciliation)",
            debit =stock_adjustments if stock_adjustments >= 0 else 0,
            credit=abs(stock_adjustments) if stock_adjustments < 0 else 0,
            indent=1, link=_stock_adj(co, fd, td, wh),
        ))

    rows += [
        R("Goods Available for Sale", debit=goods_available, indent=1),
        R("Less: Closing Stock",
          credit=closing_stock, indent=1,
          link=_stock_balance(co, fd, td, wh)),
        R("Net COGS",
          debit=cogs, bold=True,
          link=_sales_stock_entries(co, fd, td, wh)),
        spacer(),

        # ── GROSS PROFIT / LOSS ───────────────────────────────────────────────
        R("GROSS PROFIT" if gross_profit >= 0 else "GROSS LOSS",
          debit =gross_profit if gross_profit  < 0 else 0,
          credit=gross_profit if gross_profit >= 0 else 0,
          bold=True),
        spacer(),

        # ── BALANCE VERIFICATION ──────────────────────────────────────────────
        R("─" * 38, bold=False),
        R("TOTAL  (Dr = Cr confirms account balances)",
          debit=dr_total, credit=cr_total, bold=True),
        spacer(),

        # ── MARGIN ANALYSIS ───────────────────────────────────────────────────
        R(f"Gross Margin: {gm_pct:.1f}%   |   COGS Ratio: {100 - gm_pct:.1f}%",
          bold=False),
    ]

    return rows
