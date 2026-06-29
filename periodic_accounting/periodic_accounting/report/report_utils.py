"""
Shared SLE / GLE helpers for all Periodic Accounting reports.
Import with:
    from periodic_accounting.periodic_accounting.report.report_utils import ...
"""
import frappe
from frappe.utils import flt, getdate, today, add_days


# ── Warehouse / cost-centre helpers ──────────────────────────────────────────

def get_warehouses_for_cost_center(company, cost_center):
    """Non-transit warehouses linked to the given cost centre (Custom Field)."""
    return frappe.db.sql_list(
        """SELECT name FROM `tabWarehouse`
           WHERE company = %s AND cost_center = %s AND disabled = 0
             AND (warehouse_type IS NULL OR warehouse_type != 'Transit')""",
        (company, cost_center),
    )


def sle_warehouse_clause(filters, alias="sle"):
    """
    Returns (join_sql, where_fragment, param_list) for SLE queries.
    Priority: explicit warehouse → cost_centre-linked warehouses → company join.
    """
    wh = filters.get("warehouse")
    cc = filters.get("cost_center")
    co = filters.get("company") or filters.company

    if wh:
        return "", f"{alias}.warehouse = %s", [wh]

    if cc:
        whs = get_warehouses_for_cost_center(co, cc)
        if not whs:
            return "", "1 = 0", []
        ph = ", ".join(["%s"] * len(whs))
        return "", f"{alias}.warehouse IN ({ph})", list(whs)

    join = f"INNER JOIN `tabWarehouse` w ON w.name = {alias}.warehouse"
    where = (
        "w.company = %s AND w.disabled = 0 "
        "AND (w.warehouse_type IS NULL OR w.warehouse_type != 'Transit')"
    )
    return join, where, [co]


# ── Opening / Closing Stock ───────────────────────────────────────────────────

def get_opening_stock(filters):
    """
    Opening stock = closing stock of the day immediately before from_date.
    Tally logic: yesterday's closing IS today's opening — not a separate calculation.
    Uses get_closing_stock() so Bin (live) is used when the previous day is today.
    """
    prev_filters = frappe._dict({k: v for k, v in filters.items()})
    prev_filters.to_date = str(add_days(str(filters.from_date), -1))
    return get_closing_stock(prev_filters)


def get_closing_stock(filters):
    """
    Closing stock as of to_date.
    Uses tabBin (live) when to_date >= today, otherwise cumulative SLE.
    """
    td = str(filters.to_date)
    wh = filters.get("warehouse")
    cc = filters.get("cost_center")
    co = filters.get("company") or filters.company

    if getdate(td) >= getdate(today()):
        if wh:
            result = frappe.db.sql(
                "SELECT COALESCE(SUM(actual_qty * valuation_rate), 0) AS val "
                "FROM `tabBin` WHERE warehouse = %s",
                wh, as_dict=True,
            )
        elif cc:
            whs = get_warehouses_for_cost_center(co, cc)
            if not whs:
                return 0.0
            ph = ", ".join(["%s"] * len(whs))
            result = frappe.db.sql(
                f"SELECT COALESCE(SUM(actual_qty * valuation_rate), 0) AS val "
                f"FROM `tabBin` WHERE warehouse IN ({ph})",
                whs, as_dict=True,
            )
        else:
            result = frappe.db.sql(
                """SELECT COALESCE(SUM(b.actual_qty * b.valuation_rate), 0) AS val
                   FROM `tabBin` b
                   INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
                   WHERE w.company = %s AND w.disabled = 0
                     AND (w.warehouse_type IS NULL OR w.warehouse_type != 'Transit')""",
                co, as_dict=True,
            )
    else:
        join, wh_clause, wh_params = sle_warehouse_clause(filters)
        result = frappe.db.sql(
            f"""SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS val
                FROM `tabStock Ledger Entry` sle {join}
                WHERE {wh_clause}
                  AND sle.posting_date <= %s
                  AND sle.is_cancelled = 0""",
            wh_params + [td],
            as_dict=True,
        )

    return flt(result[0].val) if result else 0.0


def get_sle_stock_as_of(company, as_of_date, cost_center=None, warehouse=None):
    """
    Cumulative SLE stock value as of a specific date (always from SLE, not Bin).
    Used by the Periodic Balance Sheet.
    """
    dummy = frappe._dict(
        company=company,
        from_date=as_of_date,
        to_date=as_of_date,
        warehouse=warehouse,
        cost_center=cost_center,
    )
    join, wh_clause, wh_params = sle_warehouse_clause(dummy)
    result = frappe.db.sql(
        f"""SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS val
            FROM `tabStock Ledger Entry` sle {join}
            WHERE {wh_clause}
              AND sle.posting_date <= %s
              AND sle.is_cancelled = 0""",
        wh_params + [str(as_of_date)],
        as_dict=True,
    )
    return flt(result[0].val) if result else 0.0


# ── Stock Adjustments (SLE) ──────────────────────────────────────────────────

def get_stock_adjustments(filters):
    """
    Net SLE from Stock Entry and Stock Reconciliation in the period.
    + = stock added (Material Receipt, production return, reconciliation upward)
    - = stock consumed (Material Issue, samples, reconciliation downward)

    Required for accurate COGS formula:
        Opening  +  Net Purchases  +  Net Adjustments  -  Closing  =  Cost of Sales
    Without this term, material issues/receipts are silently absorbed into COGS.
    """
    join, wh_clause, wh_params = sle_warehouse_clause(filters)
    result = frappe.db.sql(
        f"""SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS val
            FROM `tabStock Ledger Entry` sle {join}
            WHERE {wh_clause}
              AND sle.posting_date BETWEEN %s AND %s
              AND sle.voucher_type IN ('Stock Entry', 'Stock Reconciliation')
              AND sle.is_cancelled = 0""",
        wh_params + [str(filters.from_date), str(filters.to_date)],
        as_dict=True,
    )
    return flt(result[0].val) if result else 0.0


# ── Purchases (GL — local / import classification) ───────────────────────────

def get_gl_purchase_split(filters):
    """
    Purchase breakdown from GL Entry using the chart-of-accounts classification.

    In non-perpetual inventory:
      Purchase Invoice → GL  (Dr Purchase Account, Cr AP)
      Landed Cost Voucher → GL  (Dr Landing Cost Account, Cr Supplier/Payable)

    The chart of accounts already has explicit Local Purchases / Import Purchases
    accounts and Import Landing Cost / Local Landing Cost sub-groups, so name-
    matching gives a reliable split without any custom fields.

    Returns a frappe._dict with keys:
      local_pur, import_pur, local_lc, import_lc, returns, total
    """
    co = filters.get("company") or filters.company
    fd = str(filters.from_date)
    td = str(filters.to_date)
    cc = filters.get("cost_center")
    cc_clause = " AND gle.cost_center = %s" if cc else ""
    cc_param  = [cc] if cc else []

    rows = frappe.db.sql(
        f"""SELECT
                LOWER(acc.account_name)                      AS aname,
                LOWER(COALESCE(par.account_name, ''))        AS pname,
                COALESCE(SUM(gle.debit),  0)                 AS debit,
                COALESCE(SUM(gle.credit), 0)                 AS credit
            FROM `tabGL Entry` gle
            JOIN  `tabAccount` acc ON acc.name = gle.account
            LEFT JOIN `tabAccount` par ON par.name = acc.parent_account
            WHERE gle.company = %s
              AND gle.posting_date BETWEEN %s AND %s
              AND gle.is_cancelled = 0
              AND gle.voucher_type IN (
                  'Purchase Invoice', 'Purchase Receipt', 'Landed Cost Voucher'
              )
              AND acc.root_type = 'Expense'
              AND acc.account_type IN (
                  'Cost of Goods Sold', 'Expenses Included In Valuation'
              )
              {cc_clause}
            GROUP BY acc.account_name, par.account_name""",
        [co, fd, td] + cc_param,
        as_dict=True,
    )

    local_pur = import_pur = local_lc = import_lc = returns = 0.0

    for r in rows:
        n = r.aname   # lowercase account name
        p = r.pname   # lowercase parent account name
        d = flt(r.debit)
        c = flt(r.credit)

        if 'local purchase' in n:
            local_pur  += d
            returns    += c
        elif 'import purchase' in n:
            import_pur += d
            returns    += c
        elif 'local landing' in p or 'local landing' in n:
            local_lc   += d
        elif 'import landing' in p or 'import landing' in n:
            import_lc  += d
        # Production Expenses / Other Direct Expenses are intentionally excluded;
        # they appear as Stock Adjustments (SLE) or Indirect Expenses (GL).

    total = local_pur + import_pur + local_lc + import_lc - returns
    return frappe._dict(
        local_pur  = flt(local_pur),
        import_pur = flt(import_pur),
        local_lc   = flt(local_lc),
        import_lc  = flt(import_lc),
        returns    = flt(returns),
        total      = flt(total),
    )


# ── Purchases (SLE) ───────────────────────────────────────────────────────────

def get_purchases_split(filters):
    """
    (gross_purchases, purchase_returns, net_purchases) from SLE for the period.
    Gross  = positive stock_value_difference on PI / PR / LCV.
    Returns = ABS of negative stock_value_difference on return vouchers.
    """
    join, wh_clause, wh_params = sle_warehouse_clause(filters)
    result = frappe.db.sql(
        f"""SELECT
                COALESCE(SUM(CASE WHEN sle.stock_value_difference > 0
                    THEN sle.stock_value_difference ELSE 0 END), 0) AS gross,
                COALESCE(ABS(SUM(CASE WHEN sle.stock_value_difference < 0
                    THEN sle.stock_value_difference ELSE 0 END)), 0) AS returns
            FROM `tabStock Ledger Entry` sle {join}
            WHERE {wh_clause}
              AND sle.posting_date BETWEEN %s AND %s
              AND sle.voucher_type IN (
                  'Purchase Invoice', 'Purchase Receipt', 'Landed Cost Voucher'
              )
              AND sle.is_cancelled = 0""",
        wh_params + [str(filters.from_date), str(filters.to_date)],
        as_dict=True,
    )
    if result:
        g = flt(result[0].gross)
        r = flt(result[0].returns)
        return g, r, g - r
    return 0.0, 0.0, 0.0


# ── Sales (GLE) ───────────────────────────────────────────────────────────────

def get_sales(filters):
    """
    (gross_sales, sales_returns, net_sales) from GLE.
    Income Account type — Sales Invoice / Delivery Note only.
    """
    cc = filters.get("cost_center")
    cc_clause = " AND gle.cost_center = %s" if cc else ""
    cc_param = [cc] if cc else []
    result = frappe.db.sql(
        f"""SELECT
                COALESCE(SUM(gle.credit), 0) AS gross,
                COALESCE(SUM(gle.debit),  0) AS returns
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %s
              AND gle.posting_date BETWEEN %s AND %s
              AND gle.voucher_type IN ('Sales Invoice', 'Delivery Note')
              AND gle.is_cancelled = 0
              AND acc.root_type = 'Income'
              AND acc.account_type = 'Income Account'
              {cc_clause}""",
        [filters.company, str(filters.from_date), str(filters.to_date)] + cc_param,
        as_dict=True,
    )
    if result:
        g = flt(result[0].gross)
        r = flt(result[0].returns)
        return g, r, g - r
    return 0.0, 0.0, 0.0


# ── Other Income (GLE) ───────────────────────────────────────────────────────

def get_other_income_rows(filters):
    """
    Net credits on Income root accounts from voucher types other than
    Sales Invoice / Delivery Note (those are captured in get_sales above).
    Returns list of {account, account_name, amount} dicts.
    """
    cc = filters.get("cost_center")
    cc_clause = " AND gle.cost_center = %s" if cc else ""
    cc_param = [cc] if cc else []
    rows = frappe.db.sql(
        f"""SELECT
                gle.account,
                acc.account_name,
                COALESCE(SUM(gle.credit - gle.debit), 0) AS amount
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %s
              AND gle.posting_date BETWEEN %s AND %s
              AND gle.voucher_type NOT IN ('Sales Invoice', 'Delivery Note')
              AND gle.is_cancelled = 0
              AND acc.root_type = 'Income'
              {cc_clause}
            GROUP BY gle.account, acc.account_name
            HAVING COALESCE(SUM(gle.credit - gle.debit), 0) != 0
            ORDER BY acc.account_name""",
        [filters.company, str(filters.from_date), str(filters.to_date)] + cc_param,
        as_dict=True,
    )
    return [r for r in rows if flt(r.amount) != 0]


# ── Indirect Expenses (GLE) ──────────────────────────────────────────────────

def get_purchase_expense_accounts(filters):
    """
    Expense accounts debited by Purchase Invoice / Receipt in this period.
    These represent direct stock costs already captured via SLE COGS; they must
    be excluded from Indirect Expenses to avoid double-counting.
    """
    return set(frappe.db.sql_list(
        """SELECT DISTINCT gle.account
           FROM `tabGL Entry` gle
           INNER JOIN `tabAccount` acc ON acc.name = gle.account
           WHERE gle.company = %s
             AND gle.posting_date BETWEEN %s AND %s
             AND gle.voucher_type IN ('Purchase Invoice', 'Purchase Receipt')
             AND gle.debit > 0
             AND acc.root_type = 'Expense'
             AND gle.is_cancelled = 0""",
        (filters.company, str(filters.from_date), str(filters.to_date)),
    ))


def get_indirect_expense_rows(filters, exclude_accounts=None):
    """
    Net debits on Expense root accounts, excluding purchase-related accounts
    and any Cost of Goods Sold / Stock type accounts (captured via SLE COGS).
    Returns list of {account, account_name, amount} dicts.
    """
    exclude_accounts = exclude_accounts or set()
    cc = filters.get("cost_center")
    cc_clause = " AND gle.cost_center = %s" if cc else ""
    cc_param = [cc] if cc else []

    rows = frappe.db.sql(
        f"""SELECT
                gle.account,
                acc.account_name,
                COALESCE(SUM(gle.debit - gle.credit), 0) AS amount
            FROM `tabGL Entry` gle
            INNER JOIN `tabAccount` acc ON acc.name = gle.account
            WHERE gle.company = %s
              AND gle.posting_date BETWEEN %s AND %s
              AND gle.is_cancelled = 0
              AND acc.root_type = 'Expense'
              AND acc.account_type NOT IN ('Cost of Goods Sold', 'Stock')
              {cc_clause}
            GROUP BY gle.account, acc.account_name
            HAVING COALESCE(SUM(gle.debit - gle.credit), 0) != 0
            ORDER BY acc.account_name""",
        [filters.company, str(filters.from_date), str(filters.to_date)] + cc_param,
        as_dict=True,
    )
    return [r for r in rows if flt(r.amount) != 0 and r.account not in exclude_accounts]


# ── Account tree (for Balance Sheet) ─────────────────────────────────────────

def get_account_tree_with_balances(company, root_type, as_of_date, cost_center=None):
    """
    Returns account rows ordered by lft with rolled-up GL balances as of as_of_date.
    Each dict has: name, account_name, account_number, parent_account,
                   is_group, account_type, lft, rgt, indent, own_balance, balance.
    """
    accounts = frappe.db.sql(
        """SELECT
               name, account_name, account_number, parent_account,
               is_group, account_type, lft, rgt
           FROM `tabAccount`
           WHERE company = %s AND root_type = %s AND disabled = 0
           ORDER BY lft""",
        (company, root_type),
        as_dict=True,
    )
    if not accounts:
        return []

    # Compute indent using a parent stack (O(n), single pass)
    parent_stack = []
    for a in accounts:
        while parent_stack and parent_stack[-1]["rgt"] < a["lft"]:
            parent_stack.pop()
        a["indent"] = len(parent_stack)
        parent_stack.append(a)

    # GL own-balance per account
    cc_clause = " AND cost_center = %s" if cost_center else ""
    cc_param = [cost_center] if cost_center else []
    bal_rows = frappe.db.sql(
        f"""SELECT account, COALESCE(SUM(debit - credit), 0) AS bal
            FROM `tabGL Entry`
            WHERE company = %s
              AND posting_date <= %s
              AND is_cancelled = 0
              AND voucher_type != 'Period Closing Voucher'
              {cc_clause}
            GROUP BY account""",
        [company, str(as_of_date)] + cc_param,
        as_dict=True,
    )
    bal_map = {r.account: flt(r.bal) for r in bal_rows}

    by_name = {}
    for a in accounts:
        a["own_balance"] = flt(bal_map.get(a.name, 0.0))
        a["balance"] = a["own_balance"]
        by_name[a.name] = a

    # Bottom-up rollup: children (higher lft) before parents
    for a in sorted(accounts, key=lambda x: x.lft, reverse=True):
        if a.parent_account and a.parent_account in by_name:
            by_name[a.parent_account]["balance"] += a["balance"]

    return accounts
