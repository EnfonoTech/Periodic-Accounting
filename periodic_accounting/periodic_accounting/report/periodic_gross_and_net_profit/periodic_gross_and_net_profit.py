"""
Periodic Gross and Net Profit Report
─────────────────────────────────────
ERPNext-style single-column P&L with SLE-based COGS.
Structure: Income → SLE/GL COGS → Gross Profit → Indirect Expenses → Net Profit.

COGS = Opening Stock (SLE) + Local Purchases (GL) + Import Purchases (GL)
     + Import Landing Cost (GL) + Local Landing Cost (GL)
     +/- Stock Adjustments (SLE)  − Closing Stock (SLE)

Purchase expense GL accounts are excluded from Indirect Expenses to avoid
double-counting with the GL-based cost section.
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
    get_other_income_rows,
    get_purchase_expense_accounts,
    get_indirect_expense_rows,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns(filters)
    co = filters.get("company")
    fd = filters.get("from_date")
    td = filters.get("to_date")
    if not (co and fd and td):
        return columns, []

    data, kv = build_rows(filters)
    return columns, data, None, _make_chart(kv), _make_summary(kv)


def get_columns(filters=None):
    filters = frappe._dict(filters or {})
    fd = str(filters.get("from_date") or "")
    td = str(filters.get("to_date") or "")
    period_label = f"{fd} to {td}" if fd and td else _("Amount")
    return [
        {"label": _("Particulars"),    "fieldname": "account",  "fieldtype": "Data",     "width": 330},
        {"label": "",                  "fieldname": "currency", "fieldtype": "Currency", "hidden": 1},
        {"label": period_label,        "fieldname": "amount",   "fieldtype": "Currency", "options": "currency", "width": 180},
        {"label": _("% of Net Sales"), "fieldname": "pct",      "fieldtype": "Percent",  "width": 105},
    ]


# ── URL helpers ────────────────────────────────────────────────────────────────

def _url(report, params):
    return f"/app/query-report/{report.replace(' ', '%20')}?{urlencode(params)}"

def _sb(co, sb_fd, sb_td, wh=None):
    p = {"company": co, "from_date": str(sb_fd), "to_date": str(sb_td)}
    if wh: p["warehouse"] = wh
    return _url("Stock Balance", p)

def _purchase_entries(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Purchase Stock Entries", p)

def _sales_stock_entries(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Sales Stock Entries", p)

def _sales_register(co, fd, td):
    return _url("Sales Register", {"company": co, "from_date": fd, "to_date": td})

def _stock_adj(co, fd, td, wh=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    return _url("Stock Ledger", p)

def _gl(co, fd, td, account=None, cc=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if account: p["account"] = account
    if cc:      p["cost_center"] = cc
    return _url("General Ledger", p)


# ── Main builder ───────────────────────────────────────────────────────────────

def build_rows(filters):
    co = filters.company
    fd = str(filters.from_date)
    td = str(filters.to_date)
    wh = filters.get("warehouse")
    cc = filters.get("cost_center")
    opening_date = str(add_days(fd, -1))
    currency = frappe.db.get_value("Company", co, "default_currency") or ""

    def R(label, amount=None, indent=0, is_group=False, link=None, row_type="detail", pct=None):
        return {
            "account":   label,
            "amount":    flt(amount, 3) if amount is not None else None,
            "pct":       round(pct, 1) if pct is not None else None,
            "indent":    indent,
            "is_group":  1 if is_group else 0,
            "currency":  currency,
            "link":      link,
            "_row_type": row_type,
        }

    # ── Compute figures ────────────────────────────────────────────────────────
    opening_stock                       = get_opening_stock(filters)
    closing_stock                       = get_closing_stock(filters)
    pur                                 = get_gl_purchase_split(filters)
    stock_adjustments                   = get_stock_adjustments(filters)
    gross_sales, sal_returns, net_sales = get_sales(filters)

    # COGS = Opening + Local Purchases + Import Purchases
    #      + Local Landing Cost + Import Landing Cost
    #      +/- Stock Adjustments (SE/SR)  − Closing
    goods_available = (opening_stock + pur.local_pur + pur.import_pur
                       + pur.local_lc + pur.import_lc - pur.returns
                       + stock_adjustments)
    cogs            = goods_available - closing_stock
    gross_profit    = net_sales - cogs

    other_income_rows  = get_other_income_rows(filters)
    purchase_accounts  = get_purchase_expense_accounts(filters)
    indirect_exp_rows  = get_indirect_expense_rows(filters, exclude_accounts=purchase_accounts)

    total_other_income = sum(flt(r.amount) for r in other_income_rows)
    total_indirect_exp = sum(flt(r.amount) for r in indirect_exp_rows)
    total_income       = net_sales + total_other_income
    net_profit         = gross_profit + total_other_income - total_indirect_exp

    def _p(val):
        return round(val / net_sales * 100, 1) if net_sales else None

    rows = []

    # ── INCOME ─────────────────────────────────────────────────────────────────
    rows += [
        R("Income  ← GL (Sales Invoice / Delivery Note)", is_group=True, row_type="section_header"),
        R("Gross Sales Revenue", amount=gross_sales,  indent=1,
          link=_sales_register(co, fd, td), pct=_p(gross_sales)),
        R("Less: Sales Returns", amount=-sal_returns, indent=1,
          link=_sales_register(co, fd, td), pct=_p(-sal_returns)),
    ]
    for oir in other_income_rows:
        amt = flt(oir.amount)
        rows.append(R(
            oir.account_name or oir.account, amount=amt, indent=1,
            link=_gl(co, fd, td, oir.account, cc), pct=_p(amt),
        ))
    rows += [
        R("Total Income", amount=total_income, is_group=True,
          row_type="section_total", pct=_p(total_income)),
        {},
    ]

    # ── COST OF GOODS SOLD ─────────────────────────────────────────────────────
    rows += [
        R("Cost of Goods Sold  ← SLE + GL", is_group=True, row_type="section_header"),
        R("Opening Stock",           amount=opening_stock, indent=1,
          link=_sb(co, opening_date, opening_date, wh), pct=_p(opening_stock)),
    ]

    # Purchases — show sub-lines only when they have a value
    if pur.local_pur or pur.import_pur or pur.local_lc or pur.import_lc:
        rows.append(R("Purchases  ← GL", is_group=True, indent=1, row_type="section_header"))
        if pur.local_pur:
            rows.append(R("Local Purchases",  amount=pur.local_pur,  indent=2,
                          link=_purchase_entries(co, fd, td, wh), pct=_p(pur.local_pur)))
        if pur.import_pur:
            rows.append(R("Import Purchases", amount=pur.import_pur, indent=2,
                          link=_purchase_entries(co, fd, td, wh), pct=_p(pur.import_pur)))
        if pur.import_lc:
            rows.append(R("Import Landing Cost", amount=pur.import_lc, indent=2,
                          link=_purchase_entries(co, fd, td, wh), pct=_p(pur.import_lc)))
        if pur.local_lc:
            rows.append(R("Local Landing Cost",  amount=pur.local_lc,  indent=2,
                          link=_purchase_entries(co, fd, td, wh), pct=_p(pur.local_lc)))
        if pur.returns:
            rows.append(R("Less: Purchase Returns", amount=-pur.returns, indent=2,
                          link=_purchase_entries(co, fd, td, wh), pct=_p(-pur.returns)))
        net_pur = pur.local_pur + pur.import_pur + pur.local_lc + pur.import_lc - pur.returns
        rows.append(R("Net Purchases", amount=net_pur, indent=1,
                      is_group=True, pct=_p(net_pur)))
    else:
        # Fallback when no GL purchase accounts matched (e.g. test/demo data)
        rows.append(R("Net Purchases", amount=pur.total, indent=1,
                      is_group=True, link=_purchase_entries(co, fd, td, wh),
                      pct=_p(pur.total)))

    if stock_adjustments != 0:
        rows.append(R(
            "+/- Stock Adjustments  (Stock Entry / Reconciliation)",
            amount=stock_adjustments, indent=1,
            link=_stock_adj(co, fd, td, wh), pct=_p(stock_adjustments),
        ))

    rows += [
        R("Goods Available for Sale", amount=goods_available, indent=1,
          is_group=True, pct=_p(goods_available)),
        R("Less: Closing Stock",      amount=-closing_stock,  indent=1,
          link=_sb(co, fd, td, wh), pct=_p(-closing_stock)),
        R("Net Cost of Goods Sold",   amount=cogs, is_group=True,
          row_type="section_total",
          link=_sales_stock_entries(co, fd, td, wh), pct=_p(cogs)),
        {},
    ]

    # ── GROSS PROFIT ───────────────────────────────────────────────────────────
    gm_pct = _p(gross_profit)
    rows += [
        R("Gross Profit" if gross_profit >= 0 else "Gross Loss",
          amount=gross_profit, is_group=True, row_type="gross_profit", pct=gm_pct),
        {}, {},
    ]

    # ── INDIRECT EXPENSES ──────────────────────────────────────────────────────
    if indirect_exp_rows:
        rows += [R("Indirect Expenses  ← GL (Expense accounts)",
                   is_group=True, row_type="section_header")]
        for ier in indirect_exp_rows:
            amt = flt(ier.amount)
            rows.append(R(
                ier.account_name or ier.account, amount=amt, indent=1,
                link=_gl(co, fd, td, ier.account, cc), pct=_p(amt),
            ))
        rows += [
            R("Total Indirect Expenses", amount=total_indirect_exp,
              is_group=True, row_type="section_total", pct=_p(total_indirect_exp)),
            {},
        ]

    if purchase_accounts:
        rows += [
            R(
                f"ℹ  {len(purchase_accounts)} purchase expense account(s) excluded "
                "(already captured in Cost of Goods Sold above)",
                row_type="note",
            ),
            {},
        ]

    # ── NET PROFIT ─────────────────────────────────────────────────────────────
    nm_pct = _p(net_profit)
    rows.append(R(
        "Net Profit for the Period" if net_profit >= 0 else "Net Loss for the Period",
        amount=net_profit, is_group=True, row_type="net_profit", pct=nm_pct,
    ))

    kv = {
        "gross_sales":  net_sales,
        "cogs":         cogs,
        "gross_profit": gross_profit,
        "other_income": total_other_income,
        "indirect_exp": total_indirect_exp,
        "net_profit":   net_profit,
        "gross_margin": round(gross_profit / net_sales * 100, 1) if net_sales else 0.0,
        "net_margin":   round(net_profit   / net_sales * 100, 1) if net_sales else 0.0,
        "currency":     currency,
    }
    return rows, kv


# ── Chart and summary ─────────────────────────────────────────────────────────

def _make_chart(kv):
    return {
        "data": {
            "labels": ["Net Sales", "COGS", "Gross Profit", "Indirect Exp.", "Net Profit"],
            "datasets": [{
                "name": "Amount",
                "values": [
                    flt(kv.get("gross_sales"), 2),
                    flt(kv.get("cogs"),        2),
                    max(flt(kv.get("gross_profit"), 2), 0),
                    flt(kv.get("indirect_exp"), 2),
                    max(flt(kv.get("net_profit"),   2), 0),
                ],
            }],
        },
        "type": "bar",
        "colors": ["#1565c0", "#c62828", "#2e7d32", "#e65100", "#1b5e20"],
        "fieldtype": "Currency",
    }


def _make_summary(kv):
    cur = kv.get("currency", "")
    gp  = kv.get("gross_profit", 0)
    np_ = kv.get("net_profit",   0)
    gm  = kv.get("gross_margin", 0.0)
    nm  = kv.get("net_margin",   0.0)
    return [
        {"value": kv.get("gross_sales", 0), "label": "Net Sales",                 "datatype": "Currency", "currency": cur, "indicator": "Blue"},
        {"value": gp,                        "label": f"Gross Profit ({gm:.1f}%)", "datatype": "Currency", "currency": cur, "indicator": "Green" if gp  >= 0 else "Red"},
        {"value": kv.get("indirect_exp", 0), "label": "Indirect Expenses",        "datatype": "Currency", "currency": cur, "indicator": "Orange"},
        {"value": np_,                       "label": f"Net Profit ({nm:.1f}%)",   "datatype": "Currency", "currency": cur, "indicator": "Green" if np_ >= 0 else "Red"},
    ]
