import frappe
from frappe import _
from frappe.utils import flt

from periodic_accounting.periodic_accounting.utils.gl_fetch import GLFetcher
from periodic_accounting.periodic_accounting.utils.eval_formula import eval_formula


def execute(filters=None):
    filters = frappe._dict(filters or {})

    mapper_name = filters.get("mapper")
    company     = filters.get("company")
    from_date   = filters.get("from_date")
    to_date     = filters.get("to_date")
    period_mode = filters.get("period_mode") or "Period"

    if not mapper_name:
        return _get_columns(), []

    mapper = frappe.get_doc("Report Mapper", mapper_name)

    effective_company = company or mapper.company
    effective_mode    = period_mode or mapper.period_mode or "Period"
    currency = (
        mapper.currency
        or (effective_company and frappe.db.get_value("Company", effective_company, "default_currency"))
        or frappe.defaults.get_user_default("currency")
        or ""
    )

    fetcher = GLFetcher(effective_company, from_date, to_date, currency, effective_mode)

    values   = {}
    row_defs = []

    # ── First pass: SUM lines ──────────────────────────────────────────────────
    for ln in mapper.lines:
        code = (ln.line_code or ln.label or f"LINE{ln.idx}").upper().strip()
        amt  = 0.0

        if ln.line_type == "SUM":
            accounts       = _parse_multiline(ln.accounts)
            account_groups = _parse_multiline(ln.account_groups)
            account_types  = _parse_csv(ln.account_types)

            extra = {}
            if ln.filters_json:
                try:
                    extra = frappe.parse_json(ln.filters_json) or {}
                except Exception:
                    extra = {}

            amt = fetcher.sum_accounts(
                accounts       = accounts       or None,
                account_groups = account_groups or None,
                account_types  = account_types  or None,
                include_children = bool(ln.include_children),
                extra_filters  = extra or None,
            )
            amt = amt * (1 if (ln.sign or "+1") == "+1" else -1)

        values[code] = flt(amt)
        row_defs.append({
            "code":       code,
            "label":      ln.label or ln.line_code,
            "line_type":  ln.line_type,
            "indent":     int(ln.indent or 0),
            "print_bold": bool(ln.print_bold),
            "print_italic": bool(ln.print_italic),
        })

    # ── Second pass: FORMULA / SUBTOTAL lines ──────────────────────────────────
    for ln in mapper.lines:
        code = (ln.line_code or ln.label or f"LINE{ln.idx}").upper().strip()
        if ln.line_type in ("FORMULA", "SUBTOTAL") and ln.formula:
            values[code] = eval_formula(values, ln.formula)

    # ── Build display rows ─────────────────────────────────────────────────────
    data = []
    for rd in row_defs:
        code   = rd["code"]
        amount = values.get(code, 0.0)
        indent = rd["indent"]
        label  = rd["label"] or code

        if rd["line_type"] == "BLANK":
            data.append({"label": "", "code": "", "amount": None, "currency": currency})
            continue

        data.append({
            "label":    label,
            "code":     code,
            "amount":   flt(amount, 3) if rd["line_type"] != "SECTION" else None,
            "currency": currency,
            "indent":   indent,
            "is_bold":  1 if rd["print_bold"]   else 0,
            "is_italic":1 if rd["print_italic"] else 0,
        })

    return _get_columns(from_date, to_date), data, None, None


def _get_columns(from_date=None, to_date=None):
    period = f"{from_date} to {to_date}" if from_date and to_date else _("Amount")
    return [
        {"label": _("Particulars"), "fieldname": "label",    "fieldtype": "Data",     "width": 340},
        {"label": _("Code"),        "fieldname": "code",     "fieldtype": "Data",     "width": 120},
        {"label": "",               "fieldname": "currency", "fieldtype": "Currency", "hidden": 1},
        {"label": period,           "fieldname": "amount",   "fieldtype": "Currency", "options": "currency", "width": 180},
    ]


def _parse_multiline(text):
    """Split a textarea value (newlines or commas) into a clean list."""
    if not text:
        return []
    import re
    return [t.strip() for t in re.split(r"[\n,]+", text) if t.strip()]


def _parse_csv(text):
    """Split a CSV string into a list."""
    if not text:
        return []
    return [t.strip() for t in text.split(",") if t.strip()]
