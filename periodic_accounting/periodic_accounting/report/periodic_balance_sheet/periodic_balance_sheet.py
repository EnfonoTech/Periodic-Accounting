"""
Periodic Balance Sheet
──────────────────────
ERPNext-style Balance Sheet with SLE stock override.

For non-perpetual inventory, GL stock accounts are never updated automatically.
This report replaces any 'Stock' type asset account's GL balance with the
cumulative SLE value, giving an accurate balance sheet without manual entries.

Net Profit shown under Equity uses the same SLE-based P&L formula as the
Periodic Gross and Net Profit report.
"""
import frappe
from frappe import _
from frappe.utils import flt, add_days
from urllib.parse import urlencode

from periodic_accounting.periodic_accounting.report.report_utils import (
    get_account_tree_with_balances,
    get_sle_stock_as_of,
    get_opening_stock,
    get_closing_stock,
    get_purchase_split,
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
    td = filters.get("to_date")
    fd = filters.get("from_date")
    if not (co and td and fd):
        return columns, []

    data, kv = build_balance_sheet(filters)
    return columns, data, None, None, _make_summary(kv)


def get_columns(filters=None):
    filters = frappe._dict(filters or {})
    td = str(filters.get("to_date") or "")
    period_label = f"As of {td}" if td else _("Amount")
    return [
        {"label": _("Particulars"), "fieldname": "account",  "fieldtype": "Data",     "width": 350},
        {"label": "",               "fieldname": "currency", "fieldtype": "Currency", "hidden": 1},
        {"label": period_label,     "fieldname": "amount",   "fieldtype": "Currency", "options": "currency", "width": 200},
    ]


# ── URL helpers ────────────────────────────────────────────────────────────────

def _url(report, params):
    return f"/app/query-report/{report.replace(' ', '%20')}?{urlencode(params)}"

def _gl(co, fd, td, account=None, cc=None):
    p = {"company": co, "from_date": fd, "to_date": td}
    if account: p["account"] = account
    if cc:      p["cost_center"] = cc
    return _url("General Ledger", p)

def _sb(co, sb_fd, sb_td, wh=None, cc=None):
    """Stock Balance — from_date/to_date (balance column = cumulative as of to_date)."""
    p = {"company": co, "from_date": str(sb_fd), "to_date": str(sb_td)}
    if wh: p["warehouse"] = wh
    return _url("Stock Balance", p)

def _gnp(co, fd, td, wh=None, cc=None):
    """Periodic Gross and Net Profit — shows opening/closing stock breakdown."""
    p = {"company": co, "from_date": fd, "to_date": td}
    if wh: p["warehouse"] = wh
    if cc: p["cost_center"] = cc
    return _url("Periodic Gross and Net Profit", p)


# ── Net Profit (SLE-based P&L formula) ────────────────────────────────────────

def compute_net_profit(filters):
    opening_stock     = get_opening_stock(filters)
    closing_stock     = get_closing_stock(filters)
    pur               = get_purchase_split(filters)
    stock_adjustments = get_stock_adjustments(filters)
    _, _, net_sales   = get_sales(filters)

    net_purchases = pur.local_pur + pur.import_pur + pur.landing_cost - pur.returns
    cogs          = opening_stock + net_purchases + stock_adjustments - closing_stock
    gross_profit  = net_sales - cogs

    other_income_rows = get_other_income_rows(filters)
    purchase_accounts = get_purchase_expense_accounts(filters)
    indirect_exp_rows = get_indirect_expense_rows(filters, exclude_accounts=purchase_accounts)

    total_other_income = sum(flt(r.amount) for r in other_income_rows)
    total_indirect_exp = sum(flt(r.amount) for r in indirect_exp_rows)

    return gross_profit + total_other_income - total_indirect_exp


# ── Account tree → display rows ───────────────────────────────────────────────

def _account_display_name(a):
    num  = (a.get("account_number") or "").strip()
    name = (a.get("account_name")   or a.get("name") or "").strip()
    return f"{num} - {name}" if num else name


def tree_to_rows(accounts, sign_multiplier=1, sle_overrides=None, link_fn=None, currency=""):
    """
    Convert an account tree to ERPNext-style report rows.
    sign_multiplier=1 for Assets (Dr positive), -1 for Liabilities/Equity (Cr positive).
    sle_overrides: {account_name: sle_value} to override specific account balances.
    link_fn: callable(account_dict) -> url | None; applied to leaf accounts only.
    """
    sle_overrides = sle_overrides or {}
    rows = []
    for a in accounts:
        balance = flt(a.get("balance", 0))
        if a["name"] in sle_overrides:
            balance = sle_overrides[a["name"]]

        display_balance = flt(balance * sign_multiplier, 3)
        if not a.get("is_group") and display_balance == 0:
            continue

        label    = _account_display_name(a)
        sle_note = "  ← SLE" if a["name"] in sle_overrides else ""
        is_group = bool(a.get("is_group"))

        link = None
        if not is_group and link_fn:
            link = link_fn(a)

        rows.append({
            "account":  label + sle_note,
            "amount":   display_balance if display_balance != 0 else None,
            "indent":   a.get("indent", 0),
            "is_group": 1 if is_group else 0,
            "currency": currency,
            "link":     link,
            "_account": a["name"],
            "_row_type": "section_total" if is_group else "detail",
        })
    return rows


# ── SLE stock injection ────────────────────────────────────────────────────────

def prepare_asset_rows(asset_accounts, sle_stock, sign_multiplier=1, link_fn=None, currency=""):
    """
    1. Stock-type account exists → override with SLE value, propagate diff to ancestors.
    2. No stock account → inject virtual 'Stock in Hand (SLE)' row under Current Assets.
    Returns display rows list.
    """
    by_name      = {a["name"]: a for a in asset_accounts}
    sle_overrides = {}

    stock_accounts = [a for a in asset_accounts if a.get("account_type") == "Stock"]

    if stock_accounts:
        first = True
        for sa in stock_accounts:
            old_balance = flt(sa["balance"])
            new_balance = flt(sle_stock) if first else 0.0
            first = False
            sle_overrides[sa["name"]] = new_balance
            diff = new_balance - old_balance
            if diff != 0:
                for a in asset_accounts:
                    if a["lft"] < sa["lft"] and a["rgt"] > sa["rgt"]:
                        a["balance"] += diff
    else:
        liquid_types   = {"Bank", "Cash", "Receivable"}
        liquid_parents = {
            a.get("parent_account")
            for a in asset_accounts
            if a.get("account_type") in liquid_types and a.get("parent_account")
        }
        ca_parent = next((p for p in liquid_parents if p in by_name), None)
        if not ca_parent and asset_accounts:
            ca_parent = asset_accounts[0]["name"]

        if ca_parent and ca_parent in by_name:
            parent_row = by_name[ca_parent]
            virtual = frappe._dict({
                "name":           "__sle_stock__",
                "account_name":   "Stock in Hand",
                "account_number": "",
                "parent_account": ca_parent,
                "is_group":       0,
                "account_type":   "Stock",
                "lft":            parent_row["lft"] + 1,
                "rgt":            parent_row["lft"] + 2,
                "indent":         parent_row.get("indent", 0) + 1,
                "own_balance":    flt(sle_stock),
                "balance":        flt(sle_stock),
            })
            for a in asset_accounts:
                if a["lft"] <= parent_row["lft"] and a["rgt"] >= parent_row["rgt"]:
                    a["balance"] += flt(sle_stock)
            insert_idx = next(
                (i for i, a in enumerate(asset_accounts) if a["name"] == ca_parent), -1,
            )
            asset_accounts.insert(insert_idx + 1, virtual)
            sle_overrides["__sle_stock__"] = flt(sle_stock)

    return tree_to_rows(asset_accounts, sign_multiplier, sle_overrides,
                        link_fn=link_fn, currency=currency)


# ── Main balance sheet builder ─────────────────────────────────────────────────

def build_balance_sheet(filters):
    co = filters.company
    td = str(filters.to_date)
    fd = str(filters.from_date)
    cc = filters.get("cost_center")
    wh = filters.get("warehouse")

    currency      = frappe.db.get_value("Company", co, "default_currency") or ""
    sle_stock     = get_sle_stock_as_of(co, td, cost_center=cc, warehouse=wh)
    opening_stock = get_opening_stock(filters)
    opening_date  = str(add_days(fd, -1))
    net_profit    = compute_net_profit(filters)

    asset_accounts     = get_account_tree_with_balances(co, "Asset",     td, cc)
    liability_accounts = get_account_tree_with_balances(co, "Liability", td, cc)
    equity_accounts    = get_account_tree_with_balances(co, "Equity",    td, cc)

    # ── Link helpers ──────────────────────────────────────────────────────────
    def asset_link_fn(a):
        if a.get("account_type") == "Stock" or a.get("name") == "__sle_stock__":
            return _sb(co, fd, td, wh=wh, cc=cc)
        return _gl(co, fd, td, account=a.get("name"), cc=cc)

    def gl_link_fn(a):
        return _gl(co, fd, td, account=a.get("name"), cc=cc)

    # ── Rows ──────────────────────────────────────────────────────────────────
    raw_asset_rows = prepare_asset_rows(asset_accounts, sle_stock, sign_multiplier=1,
                                        link_fn=asset_link_fn, currency=currency)

    # Inject opening/closing notes beneath the SLE-tagged stock row
    asset_rows = []
    for r in raw_asset_rows:
        asset_rows.append(r)
        if r.get("is_group") == 0 and "← SLE" in (r.get("account") or ""):
            note_indent = r.get("indent", 1) + 1
            asset_rows.append({
                "account":   f"Opening Stock  (as of {opening_date})",
                "amount":    flt(opening_stock, 3),
                "indent":    note_indent,
                "is_group":  0,
                "currency":  currency,
                "_row_type": "note",
                "link":      _sb(co, opening_date, opening_date, wh=wh, cc=cc),
            })
            asset_rows.append({
                "account":   f"Closing Stock  (as of {td})",
                "amount":    flt(sle_stock, 3),
                "indent":    note_indent,
                "is_group":  0,
                "currency":  currency,
                "_row_type": "note",
                "link":      _sb(co, fd, td, wh=wh, cc=cc),
            })

    liability_rows = tree_to_rows(liability_accounts, sign_multiplier=-1,
                                  link_fn=gl_link_fn, currency=currency)
    equity_rows    = tree_to_rows(equity_accounts,    sign_multiplier=-1,
                                  link_fn=gl_link_fn, currency=currency)

    total_assets      = flt(asset_accounts[0]["balance"])     if asset_accounts     else 0.0
    total_liabilities = flt(-liability_accounts[0]["balance"]) if liability_accounts else 0.0
    total_equity_gl   = flt(-equity_accounts[0]["balance"])    if equity_accounts    else 0.0

    total_equity_and_profit = total_equity_gl + flt(net_profit)
    balance_diff            = flt(total_assets - total_liabilities - total_equity_and_profit, 3)

    def D():
        return {}

    def sec(label):
        bar = "─" * max(0, 54 - len(label))
        return {
            "account":   f"── {label} {bar}",
            "amount":    None,
            "is_group":  1,
            "currency":  currency,
            "_row_type": "section_header",
        }

    def total(label, amount, row_type="section_total"):
        return {
            "account":   label,
            "amount":    flt(amount, 3),
            "is_group":  1,
            "currency":  currency,
            "_row_type": row_type,
        }

    np_label = "Net Profit (Period)  ← SLE" if net_profit >= 0 else "Net Loss (Period)  ← SLE"
    net_profit_row = {
        "account":   np_label,
        "amount":    flt(net_profit, 3),
        "indent":    1,
        "is_group":  0,
        "currency":  currency,
        "_row_type": "net_profit",
        "link":      _gnp(co, fd, td, wh=wh, cc=cc),
    }

    rows = (
        [sec("ASSETS"), D()]
        + asset_rows
        + [
            D(),
            total("Total Assets", total_assets, "grand_total"),
            D(), D(),
            sec("LIABILITIES"), D(),
        ]
        + liability_rows
        + [
            D(),
            total("Total Liabilities", total_liabilities),
            D(), D(),
            sec("EQUITY / CAPITAL"), D(),
        ]
        + equity_rows
        + [
            net_profit_row,
            D(),
            total("Total Equity  (incl. current period P&L)", total_equity_and_profit),
            D(), D(),
            total("Total Liabilities + Equity",
                  total_liabilities + total_equity_and_profit, "grand_total"),
            D(),
            {
                "account": (
                    "✓  Balance Sheet balanced"
                    if abs(balance_diff) <= 0.01
                    else (
                        f"⚠  Stock-GL Gap: {abs(balance_diff):,.3f}  "
                        f"(SLE closing stock not yet posted to GL. "
                        f"To reconcile: Dr Stock A/c  Cr P&L  =  {abs(balance_diff):,.3f})"
                    )
                ),
                "amount":    flt(balance_diff, 3) if abs(balance_diff) > 0.01 else None,
                "is_group":  0,
                "currency":  currency,
                "_row_type": "balance_check",
                "_balanced": abs(balance_diff) <= 0.01,
            },
        ]
    )

    kv = {
        "total_assets": total_assets,
        "total_liab":   total_liabilities,
        "total_equity": total_equity_and_profit,
        "sle_stock":    sle_stock,
        "net_profit":   net_profit,
        "balance_diff": balance_diff,
        "currency":     currency,
    }
    return rows, kv


# ── Summary ───────────────────────────────────────────────────────────────────

def _make_summary(kv):
    cur = kv.get("currency", "")
    np_ = kv.get("net_profit", 0)
    return [
        {"value": kv.get("total_assets", 0), "label": "Total Assets",  "datatype": "Currency", "currency": cur, "indicator": "Blue"},
        {"value": kv.get("sle_stock",    0), "label": "Stock (SLE)",   "datatype": "Currency", "currency": cur, "indicator": "Blue"},
        {"value": kv.get("total_liab",   0), "label": "Liabilities",   "datatype": "Currency", "currency": cur, "indicator": "Orange"},
        {"value": np_,                        "label": "Net Profit",    "datatype": "Currency", "currency": cur,
         "indicator": "Green" if np_ >= 0 else "Red"},
    ]
