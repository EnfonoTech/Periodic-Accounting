# periodic_accounting/api/restate_stock_accounts.py
"""Move already-posted stock postings from one account to another, for a date range.

Changing a Company default only affects postings made after the change: ERPNext resolves the
account when the voucher is submitted and writes the resolved account onto the GL row, so
history keeps whatever account was configured on the day. That leaves the ledger split — the
same transaction type sitting in two accounts with nothing on the documents to say why — which
is what this restates.

It rewrites the `account` on existing GL Entry rows and, where the voucher stores the account
itself, the voucher field too, so a later repost reproduces the same result instead of undoing
the work. Amounts, dates, parties, cost centres and dimensions are untouched, and no Stock
Ledger Entry is affected: only the account a value already sits under changes. Debits and
credits are therefore unchanged in total and the trial balance still balances.

This is a deliberate rewrite of posted accounting data. It is guarded accordingly:
  * System Manager or Accounts Manager only
  * dry run by default — nothing is written unless dry_run=0 is passed
  * refuses to touch a closed period (any date on or before the latest Period Closing Voucher)
  * refuses a target account belonging to another company, or a group account
  * writes a comment on every voucher it changes, naming the old and new account
  * returns the full list of what it changed, for the file

Cancelled entries are left alone: their reversal pair must keep agreeing with the original.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate


@frappe.whitelist()
def restate(company, from_date, to_date, source_accounts, target_account, dry_run=1):
    """Repoint GL entries from `source_accounts` to `target_account` within a date range.

    source_accounts: JSON list or comma-separated string of account names.
    """
    frappe.only_for(("System Manager", "Accounts Manager"))

    dry_run = cint(dry_run)
    from_date, to_date = getdate(from_date), getdate(to_date)
    if from_date > to_date:
        frappe.throw(_("From Date is after To Date."))

    sources = _as_list(source_accounts)
    if not sources:
        frappe.throw(_("No source account given."))
    if target_account in sources:
        frappe.throw(_("The target account is also a source account."))

    _validate_account(company, target_account)
    for account in sources:
        _validate_account(company, account)

    _refuse_closed_period(company, from_date)

    rows = frappe.get_all(
        "GL Entry",
        filters={
            "company": company,
            "account": ["in", sources],
            "posting_date": ["between", [from_date, to_date]],
            "is_cancelled": 0,
        },
        fields=["name", "account", "voucher_type", "voucher_no", "posting_date", "debit", "credit"],
        order_by="posting_date asc, voucher_no asc",
    )

    plan = {}
    for row in rows:
        bucket = plan.setdefault((row.voucher_type, row.voucher_no), {
            "voucher_type": row.voucher_type,
            "voucher_no": row.voucher_no,
            "posting_date": str(row.posting_date),
            "gl_rows": 0,
            "debit": 0.0,
            "credit": 0.0,
            "from_accounts": set(),
        })
        bucket["gl_rows"] += 1
        bucket["debit"] += flt(row.debit)
        bucket["credit"] += flt(row.credit)
        bucket["from_accounts"].add(row.account)

    if not dry_run:
        for row in rows:
            frappe.db.set_value("GL Entry", row.name, "account", target_account,
                                update_modified=False)
        _restate_voucher_fields(plan, sources, target_account)
        _annotate(plan, target_account)
        frappe.db.commit()

    return {
        "dry_run": bool(dry_run),
        "company": company,
        "from_date": str(from_date),
        "to_date": str(to_date),
        "target_account": target_account,
        "gl_rows": len(rows),
        "vouchers": len(plan),
        "total_debit": flt(sum(v["debit"] for v in plan.values()), 3),
        "total_credit": flt(sum(v["credit"] for v in plan.values()), 3),
        "detail": [
            dict(v, from_accounts=sorted(v["from_accounts"])) for v in plan.values()
        ],
    }


def _as_list(value):
    if isinstance(value, str):
        value = frappe.parse_json(value) if value.strip().startswith("[") else value.split(",")
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def _validate_account(company, account):
    row = frappe.db.get_value("Account", account, ["company", "is_group"], as_dict=True)
    if not row:
        frappe.throw(_("Account %s does not exist.") % frappe.bold(account))
    if row.company != company:
        frappe.throw(_("Account %(acc)s belongs to %(co)s.")
                     % {"acc": frappe.bold(account), "co": row.company})
    if cint(row.is_group):
        frappe.throw(_("Account %s is a group account.") % frappe.bold(account))


def _refuse_closed_period(company, from_date):
    """A closed period is closed: its balances have already been carried to retained earnings.

    Period Closing Voucher carries `period_end_date` (v15) — it has no `posting_date`, so the
    field is resolved from the meta rather than assumed, and a version that names it differently
    degrades to skipping the guard rather than raising on a missing column.
    """
    meta = frappe.get_meta("Period Closing Voucher")
    field = next((f for f in ("period_end_date", "transaction_date", "posting_date")
                  if meta.has_field(f)), None)
    if not field:
        return

    closed = frappe.get_all(
        "Period Closing Voucher",
        filters={"company": company, "docstatus": 1},
        pluck=field,
        order_by="%s desc" % field,
        limit=1,
    )
    if not closed or not closed[0]:
        return

    if getdate(from_date) <= getdate(closed[0]):
        frappe.throw(
            _("The period is closed to %s by a Period Closing Voucher. Restating a closed "
              "period would leave the closing entry disagreeing with the accounts it closed.")
            % frappe.bold(str(closed[0]))
        )


def _restate_voucher_fields(plan, sources, target_account):
    """Keep the voucher's own stored account in step, so a repost does not undo this.

    Only Purchase Invoice and the stock vouchers store the account; a Purchase Receipt resolves
    the company default when its entries are built, so a repost of one already follows the new
    default and nothing needs stamping.
    """
    for (voucher_type, voucher_no) in plan:
        if voucher_type == "Purchase Invoice":
            if frappe.db.get_value("Purchase Invoice", voucher_no, "stock_received_but_not_billed") in sources:
                frappe.db.set_value("Purchase Invoice", voucher_no,
                                    "stock_received_but_not_billed", target_account,
                                    update_modified=False)

        elif voucher_type == "Stock Reconciliation":
            if frappe.db.get_value("Stock Reconciliation", voucher_no, "expense_account") in sources:
                frappe.db.set_value("Stock Reconciliation", voucher_no,
                                    "expense_account", target_account, update_modified=False)

        elif voucher_type == "Stock Entry":
            for row in frappe.get_all("Stock Entry Detail",
                                      filters={"parent": voucher_no, "expense_account": ["in", sources]},
                                      pluck="name"):
                frappe.db.set_value("Stock Entry Detail", row, "expense_account",
                                    target_account, update_modified=False)


def _annotate(plan, target_account):
    """Every restated voucher says on its own timeline what was done to it, and by whom."""
    for entry in plan.values():
        try:
            doc = frappe.get_doc(entry["voucher_type"], entry["voucher_no"])
            doc.add_comment(
                "Comment",
                _("Ledger restated: %(rows)s GL row(s) moved from %(old)s to %(new)s by %(who)s.")
                % {
                    "rows": entry["gl_rows"],
                    "old": ", ".join(sorted(entry["from_accounts"])),
                    "new": frappe.bold(target_account),
                    "who": frappe.session.user,
                },
            )
        except Exception:
            # a note is worth having, but never at the cost of the restatement itself
            frappe.log_error(
                message=frappe.get_traceback(),
                title="periodic_accounting: could not annotate %s" % entry["voucher_no"],
            )
