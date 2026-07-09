import re

_TOKEN = re.compile(r"\b[A-Z0-9_]+\b")


def eval_formula(values: dict, expr: str) -> float:
    """
    Safely evaluate a formula string where UPPER_CASE tokens are replaced
    by their numeric values from the `values` dict.

    Example:
        values = {"SALES": 100, "COGS": 60}
        eval_formula(values, "SALES - COGS")  →  40.0

    Only arithmetic operators are allowed; no builtins are exposed.
    Unknown tokens resolve to 0.
    """
    def repl(m):
        key = m.group(0)
        if key in values:
            return str(float(values[key]))
        if key.isdigit():
            return key
        return "0"

    safe = _TOKEN.sub(repl, (expr or "").upper())
    try:
        return float(eval(safe, {"__builtins__": {}}, {}))  # noqa: S307
    except Exception:
        return 0.0
