import frappe
from frappe.utils import getdate


class GLFetcher:
    """
    Fetches and sums GL Entry amounts for the Mapped Financial Report.
    Supports Period mode (between from_date and to_date) or YTD (up to to_date).
    """

    def __init__(self, company, from_date, to_date, currency=None, period_mode="Period"):
        self.company     = company
        self.from_date   = str(getdate(from_date)) if from_date else None
        self.to_date     = str(getdate(to_date))   if to_date   else None
        self.currency    = currency
        self.period_mode = period_mode

    def _date_filter(self):
        if not (self.from_date or self.to_date):
            return {}
        if self.period_mode == "YTD":
            return {"posting_date": ("<=", self.to_date)}
        return {"posting_date": ("between", [self.from_date, self.to_date])}

    def sum_accounts(self, *, accounts=None, account_groups=None, account_types=None,
                     include_children=True, extra_filters=None) -> float:
        """
        Returns debit − credit sum for the matched GL Entry rows.

        accounts        : list of specific account names
        account_groups  : list of parent account names — all leaf children are included
        account_types   : list of account_type strings (e.g. ['Income Account'])
        include_children: when True, expand account groups to leaf accounts
        extra_filters   : dict of additional frappe.get_all filters
        """
        account_names = set(accounts or [])

        if account_groups and include_children:
            for group in account_groups:
                lft, rgt = frappe.db.get_value("Account", group, ["lft", "rgt"]) or (None, None)
                if lft is None:
                    continue
                children = frappe.get_all(
                    "Account", pluck="name",
                    filters={"is_group": 0, "lft": (">=", lft), "rgt": ("<=", rgt)},
                )
                account_names.update(children)

        if account_types:
            typed = frappe.get_all(
                "Account", pluck="name",
                filters={
                    "account_type": ("in", [t.strip() for t in account_types if t.strip()]),
                    "company":      self.company,
                },
            )
            account_names.update(typed)

        filters = {"docstatus": 1, "is_cancelled": 0}
        if self.company:
            filters["company"] = self.company
        filters.update(self._date_filter())
        if account_names:
            filters["account"] = ("in", list(account_names))
        if extra_filters:
            filters.update(extra_filters)

        rows = frappe.get_all(
            "GL Entry",
            fields=["sum(debit) as debit", "sum(credit) as credit"],
            filters=filters,
        )
        if not rows:
            return 0.0
        row    = rows[0]
        debit  = float(row.get("debit")  or 0)
        credit = float(row.get("credit") or 0)
        return debit - credit
