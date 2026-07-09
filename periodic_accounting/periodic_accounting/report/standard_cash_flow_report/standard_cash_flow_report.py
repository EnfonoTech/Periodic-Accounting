"""
Standard Cash Flow Report (Indirect Method)
GL-based, configurable via Cash Flow Mapper / Cash Flow Mapping DocTypes.
Each line row carries _accounts / _link_type for JS drill-down.
"""
import frappe
from frappe import _
from frappe.utils import flt, add_days

from periodic_accounting.periodic_accounting.report.report_utils import (
    get_opening_stock,
    get_closing_stock,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    # Accept both ERPNext-style period_start/end_date and simple from/to_date
    if not filters.get("period_start_date") and filters.get("from_date"):
        filters.period_start_date = filters.from_date
    if not filters.get("period_end_date") and filters.get("to_date"):
        filters.period_end_date = filters.to_date
    columns = _columns(filters)
    if not (filters.get("company") and filters.get("period_start_date") and filters.get("period_end_date")):
        return columns, []
    data, summary_data = _build(filters)
    return columns, data, None, None, _summary(summary_data)


# ── columns ───────────────────────────────────────────────────────────────────

def _columns(filters=None):
    filters = frappe._dict(filters or {})
    fd = str(filters.get("period_start_date") or filters.get("from_date") or "")
    td = str(filters.get("period_end_date") or filters.get("to_date") or "")
    period = f"{fd} to {td}" if fd and td else _("Amount")
    return [
        {"label": _("Particulars"), "fieldname": "account",  "fieldtype": "Data",     "width": 380},
        {"label": "",               "fieldname": "currency", "fieldtype": "Currency", "hidden": 1},
        {"label": period,           "fieldname": "amount",   "fieldtype": "Currency", "options": "currency", "width": 180},
    ]


# ── GL helpers ────────────────────────────────────────────────────────────────

def _fb(filters):
    """Finance book clause honoring include_default_book_entries."""
    fb = filters.get("finance_book") if isinstance(filters, dict) else filters
    include_default = True
    if isinstance(filters, dict):
        include_default = bool(int(filters.get("include_default_book_entries", 1) or 1))
    if fb:
        if include_default:
            return (
                " AND (gle.finance_book = %s OR gle.finance_book IS NULL OR gle.finance_book = '')",
                [fb],
            )
        return " AND gle.finance_book = %s", [fb]
    return "", []


def _extra(filters):
    """Optional cost_center / project GL clauses."""
    clauses, params = [], []
    if isinstance(filters, dict):
        if filters.get("cost_center"):
            clauses.append("gle.cost_center = %s")
            params.append(filters.cost_center)
        if filters.get("project"):
            clauses.append("gle.project = %s")
            params.append(filters.project)
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


def _gl_root(co, fd, td, root_type, cmd=True, filters=None):
    fbc, fbp = _fb(filters or {})
    exc, exp = _extra(filters or {})
    sign = "credit - debit" if cmd else "debit - credit"
    r = frappe.db.sql(
        f"""SELECT COALESCE(SUM({sign}), 0) AS val
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %s AND gle.posting_date BETWEEN %s AND %s
              AND acc.root_type = %s AND gle.is_cancelled = 0
              AND gle.voucher_type != 'Period Closing Voucher' {fbc}{exc}""",
        [co, fd, td, root_type] + fbp + exp, as_dict=True,
    )
    return flt(r[0].val) if r else 0.0


def _gl_type(co, fd, td, account_type, cmd=True, filters=None):
    fbc, fbp = _fb(filters or {})
    exc, exp = _extra(filters or {})
    sign = "credit - debit" if cmd else "debit - credit"
    r = frappe.db.sql(
        f"""SELECT COALESCE(SUM({sign}), 0) AS val
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %s AND gle.posting_date BETWEEN %s AND %s
              AND acc.account_type = %s AND gle.is_cancelled = 0
              AND gle.voucher_type != 'Period Closing Voucher' {fbc}{exc}""",
        [co, fd, td, account_type] + fbp + exp, as_dict=True,
    )
    return flt(r[0].val) if r else 0.0


def _gl_accounts(co, fd, td, accounts, cmd=True, filters=None):
    if not accounts:
        return 0.0
    ph = ", ".join(["%s"] * len(accounts))
    fbc, fbp = _fb(filters or {})
    exc, exp = _extra(filters or {})
    sign = "credit - debit" if cmd else "debit - credit"
    r = frappe.db.sql(
        f"""SELECT COALESCE(SUM({sign}), 0) AS val
            FROM `tabGL Entry` gle
            WHERE gle.company = %s AND gle.posting_date BETWEEN %s AND %s
              AND gle.account IN ({ph}) AND gle.is_cancelled = 0
              AND gle.voucher_type != 'Period Closing Voucher' {fbc}{exc}""",
        [co, fd, td] + list(accounts) + fbp + exp, as_dict=True,
    )
    return flt(r[0].val) if r else 0.0


def _cash_balance(co, as_of, filters=None):
    fbc, fbp = _fb(filters or {})
    r = frappe.db.sql(
        f"""SELECT COALESCE(SUM(debit - credit), 0) AS val
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %s AND gle.posting_date <= %s
              AND acc.account_type IN ('Bank', 'Cash') AND gle.is_cancelled = 0
              AND gle.voucher_type != 'Period Closing Voucher' {fbc}""",
        [co, str(as_of)] + fbp, as_dict=True,
    )
    return flt(r[0].val) if r else 0.0


def _accts_by_type(co, account_type):
    return frappe.db.get_all(
        "Account",
        filters={"company": co, "account_type": account_type, "is_group": 0, "disabled": 0},
        pluck="name",
    )


# ── mapper helpers ────────────────────────────────────────────────────────────

def _mappers_configured():
    # NOTE: table_exists() prepends "tab" itself — passing "tabCash Flow Mapper"
    # checked for "tabtabCash Flow Mapper" and silently disabled mappers forever.
    if not frappe.db.table_exists("Cash Flow Mapper"):
        return False
    if not frappe.db.exists("Cash Flow Mapper", "Operating Activities"):
        return False
    return bool(frappe.db.count("Cash Flow Mapper Item", {"parent": "Operating Activities"}))


def _compute_mapping(mapping_name, filters):
    m   = frappe.get_cached_doc("Cash Flow Mapping", mapping_name)
    co  = filters.company
    fd  = str(filters.get("period_start_date") or filters.get("from_date"))
    td  = str(filters.get("period_end_date") or filters.get("to_date"))
    ct  = m.calculation_type or "GL: credit minus debit"

    if ct == "SLE: inventory change":
        return flt(get_opening_stock(filters) - get_closing_stock(filters))

    accounts = [row.account for row in (m.accounts or []) if row.account]
    cmd = (ct == "GL: credit minus debit")
    return _gl_accounts(co, fd, td, accounts, cmd=cmd, filters=filters) if accounts else 0.0


def _mapping_accounts(mapping_name):
    """Return GL accounts for drill-down (empty for SLE-based mappings)."""
    m = frappe.get_cached_doc("Cash Flow Mapping", mapping_name)
    if (m.calculation_type or "") == "SLE: inventory change":
        return []
    return [row.account for row in (m.accounts or []) if row.account]


def _mapper_footer(section_name, default):
    if frappe.db.exists("Cash Flow Mapper", section_name):
        return frappe.db.get_value("Cash Flow Mapper", section_name, "section_footer") or default
    return default


# ── build ─────────────────────────────────────────────────────────────────────

def _build(filters):
    co       = filters.company
    fd       = str(filters.get("period_start_date") or filters.get("from_date"))
    td       = str(filters.get("period_end_date") or filters.get("to_date"))
    currency = frappe.db.get_value("Company", co, "default_currency") or ""
    cfgd     = _mappers_configured()

    def R(label, amount=None, indent=0, bold=False, section=False, blank=False):
        return {
            "account":  "" if blank else label,
            "amount":   flt(amount, 3) if (amount is not None and not section and not blank) else None,
            "currency": currency,
            "indent":   indent,
            "is_group": 1 if (bold or section) else 0,
        }

    rows    = []
    summary = {}

    # Net Profit (GL-based)
    income     = _gl_root(co, fd, td, "Income",  cmd=True,  filters=filters)
    expense    = _gl_root(co, fd, td, "Expense", cmd=False, filters=filters)
    net_profit = income - expense

    # ── A. Operating Activities ───────────────────────────────────────────────
    rows.append(R("A.  Cash Flows from Operating Activities", section=True))

    np_row = R(_("Net Profit / (Loss) for the Period"), net_profit, indent=1)
    np_row["_link_type"] = "profit_loss"
    rows.append(np_row)

    op_amounts = []

    if cfgd:
        mapper   = frappe.get_cached_doc("Cash Flow Mapper", "Operating Activities")
        adj_list = []
        wc_list  = []

        for item in mapper.mapping:
            mdoc     = frappe.get_cached_doc("Cash Flow Mapping", item.mapping)
            label    = getattr(item, "label_override", None) or mdoc.label or item.mapping
            amount   = _compute_mapping(item.mapping, filters)
            accounts = _mapping_accounts(item.mapping)
            entry    = (label, amount, accounts)
            if mdoc.is_working_capital:
                wc_list.append(entry)
            else:
                adj_list.append(entry)

        if adj_list:
            rows.append(R(_("Adjustments for Non-Cash Items:"), indent=1, bold=True))
            for lbl, amt, accts in adj_list:
                row = R(lbl, amt, indent=2)
                if accts:
                    row["_accounts"] = accts
                rows.append(row)
                op_amounts.append(amt)

        if wc_list:
            rows.append(R(_("Working Capital Changes:"), indent=1, bold=True))
            for lbl, amt, accts in wc_list:
                row = R(lbl, amt, indent=2)
                if accts:
                    row["_accounts"] = accts
                rows.append(row)
                op_amounts.append(amt)
    else:
        depr  = _gl_type(co, fd, td, "Depreciation", cmd=False, filters=filters)
        recv  = _gl_type(co, fd, td, "Receivable",   cmd=True,  filters=filters)
        pay   = _gl_type(co, fd, td, "Payable",       cmd=True,  filters=filters)
        stock = _gl_type(co, fd, td, "Stock",          cmd=True,  filters=filters)

        rows.append(R(_("Adjustments for Non-Cash Items:"), indent=1, bold=True))
        row = R(_("Depreciation"), depr, indent=2)
        row["_accounts"] = _accts_by_type(co, "Depreciation")
        rows.append(row)

        rows.append(R(_("Working Capital Changes:"), indent=1, bold=True))

        row = R(_("Net Change in Accounts Receivable"), recv, indent=2)
        row["_accounts"] = _accts_by_type(co, "Receivable")
        rows.append(row)

        row = R(_("Net Change in Accounts Payable"), pay, indent=2)
        row["_accounts"] = _accts_by_type(co, "Payable")
        rows.append(row)

        row = R(_("Net Change in Inventory"), stock, indent=2)
        row["_accounts"] = _accts_by_type(co, "Stock")
        rows.append(row)

        op_amounts = [depr, recv, pay, stock]

    net_ops    = flt(net_profit) + sum(flt(v) for v in op_amounts)
    op_footer  = _mapper_footer("Operating Activities", _("Net Cash from Operating Activities"))
    rows.append(R(op_footer, net_ops, bold=True))
    summary[op_footer] = net_ops
    rows.append(R("", blank=True))

    # ── B. Investing Activities ───────────────────────────────────────────────
    rows.append(R("B.  Cash Flows from Investing Activities", section=True))
    inv_amounts = []

    if cfgd and frappe.db.exists("Cash Flow Mapper", "Investing Activities"):
        mapper = frappe.get_cached_doc("Cash Flow Mapper", "Investing Activities")
        for item in mapper.mapping:
            mdoc     = frappe.get_cached_doc("Cash Flow Mapping", item.mapping)
            label    = getattr(item, "label_override", None) or mdoc.label or item.mapping
            amount   = _compute_mapping(item.mapping, filters)
            accounts = _mapping_accounts(item.mapping)
            row      = R(label, amount, indent=1)
            if accounts:
                row["_accounts"] = accounts
            rows.append(row)
            inv_amounts.append(amount)
        inv_footer = mapper.section_footer or _("Net Cash from Investing Activities")
    else:
        fa  = _gl_type(co, fd, td, "Fixed Asset", cmd=True, filters=filters)
        row = R(_("Net Change in Fixed Assets"), fa, indent=1)
        row["_accounts"] = _accts_by_type(co, "Fixed Asset")
        rows.append(row)
        inv_amounts = [fa]
        inv_footer  = _("Net Cash from Investing Activities")

    net_inv = sum(flt(v) for v in inv_amounts)
    rows.append(R(inv_footer, net_inv, bold=True))
    summary[inv_footer] = net_inv
    rows.append(R("", blank=True))

    # ── C. Financing Activities ───────────────────────────────────────────────
    rows.append(R("C.  Cash Flows from Financing Activities", section=True))
    fin_amounts = []

    if cfgd and frappe.db.exists("Cash Flow Mapper", "Financing Activities"):
        mapper = frappe.get_cached_doc("Cash Flow Mapper", "Financing Activities")
        for item in mapper.mapping:
            mdoc     = frappe.get_cached_doc("Cash Flow Mapping", item.mapping)
            label    = getattr(item, "label_override", None) or mdoc.label or item.mapping
            amount   = _compute_mapping(item.mapping, filters)
            accounts = _mapping_accounts(item.mapping)
            row      = R(label, amount, indent=1)
            if accounts:
                row["_accounts"] = accounts
            rows.append(row)
            fin_amounts.append(amount)
        fin_footer = mapper.section_footer or _("Net Cash from Financing Activities")
    else:
        eq  = _gl_type(co, fd, td, "Equity", cmd=True, filters=filters)
        row = R(_("Net Change in Equity"), eq, indent=1)
        row["_accounts"] = _accts_by_type(co, "Equity")
        rows.append(row)
        fin_amounts = [eq]
        fin_footer  = _("Net Cash from Financing Activities")

    net_fin = sum(flt(v) for v in fin_amounts)
    rows.append(R(fin_footer, net_fin, bold=True))
    summary[fin_footer] = net_fin
    rows.append(R("", blank=True))

    # ── Net Change in Cash ────────────────────────────────────────────────────
    net_change = net_ops + net_inv + net_fin
    rows.append(R(_("Net Change in Cash and Cash Equivalents"), net_change, bold=True))
    summary[_("Net Change in Cash")] = net_change

    # ── Opening / Closing Balance (optional) ──────────────────────────────────
    if filters.get("show_opening_and_closing_balance"):
        cash_accts = _accts_by_type(co, "Bank") + _accts_by_type(co, "Cash")
        opening    = _cash_balance(co, str(add_days(fd, -1)), filters=filters)
        closing    = _cash_balance(co, td, filters=filters)

        row = R(f"Opening Cash & Bank Balance  (as of {add_days(fd, -1)})", opening, indent=1)
        row["_accounts"] = cash_accts
        rows.append(row)

        row = R(f"Closing Cash & Bank Balance  (as of {td})", closing, indent=1)
        row["_accounts"] = cash_accts
        rows.append(row)

        summary[_("Opening Cash Balance")] = opening
        summary[_("Closing Cash Balance")] = closing

    return rows, summary


# ── summary cards ─────────────────────────────────────────────────────────────

def _summary(summary_data):
    result = []
    for label, value in summary_data.items():
        d = {"label": label, "value": value, "datatype": "Currency", "currency": ""}
        if _("Net Change") in label or _("Net Cash") in label:
            d["indicator"] = "Green" if flt(value) >= 0 else "Red"
        result.append(d)
    return result
