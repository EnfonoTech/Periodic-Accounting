# Periodic Accounting — Features

ERPNext app for companies using Periodic Inventory. Covers the period-end posting workflow, live trading account visibility, and two reports for verifying inventory accuracy and COGS.

---

## Features

| # | Feature | Type | Path |
|---|---------|------|------|
| 1 | [Periodic Accounting Entry](#1-periodic-accounting-entry) | DocType (submittable) | Periodic Accounting → Periodic Accounting Entry |
| 2 | [Realtime Trading Account Report](#2-realtime-trading-account-report) | Script Report | Accounts → Reports → Realtime Trading Account |
| 3 | [Audit Trading Account Report](#3-audit-trading-account-report) | Script Report | Accounts → Reports → Audit Trading Account Report |
| 4 | [Item COGS Analysis Report](#4-item-cogs-analysis-report) | Script Report | Accounts → Reports → Item COGS Analysis Report |
| 5 | [Audit Guide Page](#5-audit-guide-page) | Desk Page | `/app/audit-guide` |

---

## 1. Periodic Accounting Entry

Posts the period-end journal entry that recognises closing stock on the Balance Sheet and establishes COGS through the Trading Account structure.

### How It Works

In Periodic Inventory mode, purchases are expensed immediately (Dr Purchases / Cr AP) and stock movements create no GL entries. The Stock-in-Hand asset account is only updated at period-end. COGS is derived implicitly:

```
COGS = Opening Stock  +  Net Purchases  −  Closing Stock
```

The entry computes: **net change = tabBin closing value − Stock-in-Hand GL balance**

| Scenario | Journal Entry |
|---|---|
| Closing > Opening | Dr Stock-in-Hand (BS) / Cr Closing Stock (IS) |
| Closing < Opening | Dr Closing Stock (IS) / Cr Stock-in-Hand (BS) |

### Fields

| Field | Description |
|---|---|
| Company | Filters accounts and warehouses |
| Posting Date | Date stamped on the linked Journal Entry |
| Cost Center | Attribution tag on every JE row; does not filter warehouses |
| For All Stock Accounts | Pulls every Stock-type account automatically |
| Closing Stock Account (IS) | Income-type account for the closing stock movement |
| Accounts Table | Populated by **Get Balance**: GL balance, Bin balance, and net change per account |

### Workflow

1. Open **Periodic Accounting Entry → New**
2. Set Company, Posting Date, Cost Center (optional)
3. Tick **For All Stock Accounts** or select accounts manually
4. Click **Get Balance** — queries `tabBin` and GL per account
5. Review the net change per account
6. **Submit** — linked Journal Entry is auto-created and submitted

### Constraints

- Rejected if **Enable Perpetual Inventory** is on for the company
- Closing Stock Account must have `root_type = Income`
- Stock-in-Hand Account must be a `Stock` type asset account
- Amend is supported: cancels the linked JE and recreates it

### Required Chart of Accounts

| Account | Root Type | Account Type | Purpose |
|---|---|---|---|
| Stock-in-Hand | Asset | Stock | Recognised closing stock on Balance Sheet |
| Closing Stock (Income Statement) | Income | Income Account | Credited on increase, debited on decrease |
| Purchases | Expense | — | All purchase invoices route here — never to Stock-in-Hand |

> Full setup guide and worked example: [PERIODIC_ACCOUNTING.md](PERIODIC_ACCOUNTING.md)

---

## 2. Realtime Trading Account Report

Shows the current period's trading position built from Stock Ledger Entries and GL, without waiting for the period-end entry to be posted.

### Filters

| Filter | Required | Default |
|---|---|---|
| Company | Yes | — |
| From Date | Yes | Month start |
| To Date | Yes | Today |
| Warehouse | No | All |

### Report Structure

```
INCOME
  Gross Sales Revenue        ← GL credits on income accounts (SI / DN)
  Less: Sales Returns        ← GL debits on income accounts
  NET SALES REVENUE

COST OF GOODS SOLD
  Opening Stock              ← Cumulative SLE before from_date
  Add: Gross Purchases       ← Positive SLE differences (PI / PR)
  Less: Purchase Returns     ← Negative SLE differences
  Net Purchases
  Goods Available for Sale
  Less: Closing Stock        ← tabBin (live) or cumulative SLE (historical)
  NET COGS

GROSS PROFIT
```

### Data Sources

- Sales figures from GL entries on income accounts (Sales Invoices, Delivery Notes)
- Stock figures from Stock Ledger Entries (`stock_value_difference`), not from GL accounts

---

## 3. Audit Trading Account Report

Reconstructs the trading account from Stock Ledger Entries and reconciles it against the General Ledger. Produces two pass/fail checks that must both be clean before closing a period.

### Filters

| Filter | Required | Default |
|---|---|---|
| Company | Yes | User's company |
| From Date | Yes | Month start |
| To Date | Yes | Today |
| Warehouse | No | All |
| Cost Center | No | All |
| Breakdown By | No | None (options: Warehouse, Item Group) |

### Report Output

**Summary strip** at top of report:

| Indicator | Calculation |
|---|---|
| Net Sales | Total sales revenue for the period |
| COGS | Formula COGS from SLE |
| Gross Profit | Net Sales − COGS |
| Gross Margin % | Gross Profit ÷ Net Sales × 100 |

**Bar chart** — Opening Stock, Net Purchases, Closing Stock, Formula COGS, Net Sales, Gross Profit side-by-side.

**Main table:**

| Section | Rows |
|---|---|
| SALES | Gross Sales, Sales Returns, Net Sales |
| COST OF GOODS SOLD | Opening Stock; Local PR, Import PR, LCV, PI Rate Adj, Purchase Returns, Transfer In/Out, Mfg/Issue Out, Sales COGS, Sales Returns In; Closing Stock; Formula COGS |
| GROSS PROFIT | Net Sales − Formula COGS |
| GL Reconciliation | COGS Variance ✅/❌; Bin vs Stock Account GL ✅/❌ |
| Breakdown | Per-warehouse or per-item-group sub-totals (when filter is set) |

### Purchase Split

Purchases are broken into five lines using SLE `voucher_type` and currency:

| Line | Source | Filter |
|---|---|---|
| Local PR | Purchase Receipt | Company default currency |
| Import PR | Purchase Receipt | Foreign currency |
| Landed Cost Voucher | Landed Cost Voucher | — |
| PI Rate Adjustment | Purchase Invoice | Net of PR values |
| Purchase Returns | Purchase Receipt (negative SLE) | — |

### Two Reconciliation Checks

| Check | Passes When | Fails When |
|---|---|---|
| COGS Variance | Formula COGS (SLE) = GL COGS | Perpetual inventory off; backdated LCV posted after delivery; manual GL adjustment |
| Bin vs Stock Account GL | Live Bin value = GL Stock Account balance | Voucher cancelled without GL reversal; direct journal posted to stock account |

---

## 4. Item COGS Analysis Report

Shows one row per item with a full stock movement breakdown for the period. Two columns — **Variance** and **COGS Diff** — must both be zero for every item before period-end sign-off.

### Filters

| Filter | Required | Default |
|---|---|---|
| Company | Yes | User's company |
| From Date | Yes | Month start |
| To Date | Yes | Today |
| Warehouse | No | All |
| Cost Center | No | All (affects GL COGS column only) |
| Item Group | No | All |
| Item | No | All |
| Hide Fully-Zero Rows | No | Off |

### Columns

| Column | Source | What it represents |
|---|---|---|
| Item Code / Name | Item master | — |
| Opening | Cumulative SLE before from_date | Stock value carried in from prior period |
| Local PR | SLE — Purchase Receipt, company currency | Domestic purchases received |
| Import PR | SLE — Purchase Receipt, foreign currency | Imported goods received |
| LCV | SLE — Landed Cost Voucher | Freight, customs, and other landed costs |
| PI Rate Adj | SLE — Purchase Invoice | Difference when invoice rate ≠ receipt rate |
| Pur Returns | SLE — Purchase Receipt (negative) | Purchase returns and rejections |
| Transfer In | SLE — Material Transfer | Stock moved in from another warehouse |
| Transfer Out | SLE — Material Transfer | Stock moved out to another warehouse |
| Mfg / Issue Out | SLE — Work Order, Material Issue | Stock consumed in production or issued out |
| Sales COGS | SLE — Sales Invoice, Delivery Note (negative) | Stock value reduced on sale |
| Sales Ret In | SLE — Sales Return | Stock value recovered on sales return |
| Closing | tabBin (live) or cumulative SLE | Closing stock value for the period |
| **Variance** | Opening + Inflows − Outflows − Closing | Stock equation balance — must be 0.000 |
| GL COGS | GL Dr entries on COGS accounts | COGS posted by the perpetual engine |
| **COGS Diff** | Sales COGS − GL COGS | SLE vs GL agreement — must be 0.000 |

### Stock Equation

```
Opening
  + Local PR + Import PR + LCV + PI Adj + Transfer In + Sales Ret In
  − Pur Returns − Transfer Out − Mfg Out − Sales COGS
  − Closing
  = Variance   (must be 0)
```

### Column Indicators

| Value | Variance | COGS Diff |
|---|---|---|
| ≈ 0.000 | ✓ green | ✓ green |
| Non-zero | ⚠ red pill | △ amber pill |

### Report Extras

- **Summary strip**: Total Sales COGS, Total Net Purchases, Gross Profit, Gross Margin %
- **Bar chart**: Top-12 items by Sales COGS — Sales COGS vs Net Purchases
- **Column freeze**: Item Code, Item Name, Item Group stay fixed while the rest scroll

---

## 5. Audit Guide Page

In-app reference page for the audit workflow. Accessible at `/app/audit-guide` (Accounts Manager or Accounts User role required).

### Contents

| Section | Description |
|---|---|
| Audit Workflow | Six-step process from setting the period to signing off |
| 4 Checks — Trading Account | COGS Variance, Bin vs GL, Gross Profit reasonableness, Period continuity |
| Purchase Split Guide | What each purchase line represents and how to verify it |
| Column Guide — Item COGS | All 17 columns with the audit action for each non-zero value |
| Filter Usage | When to use Warehouse, Item Group, Cost Center, and Hide-Zero filters |
| Cross-referencing Reports | How to trace a Trading Account variance to the specific item in Item COGS |
| Common Issues & Fixes | Symptom → cause → remediation table |
| Period-End Checklist | 13-item sign-off list |

Quick-launch toolbar buttons open each report directly from the guide.

---

## Auditing with These Reports

### What the Two Reports Verify

The two audit reports test the same financial data from different angles:

| | Audit Trading Account | Item COGS Analysis |
|---|---|---|
| Scope | Company total for the period | Per item for the period |
| Stock source | Stock Ledger Entries | Stock Ledger Entries |
| GL source | GL entries on COGS and stock accounts | GL Dr entries on COGS accounts |
| Primary checks | COGS Variance, Bin vs GL | Variance per item, COGS Diff per item |
| Use case | Is there a problem this period? | Which item caused it? |

Run the Trading Account first to determine whether the period is clean. If either reconciliation check fails, run Item COGS Analysis to isolate the source.

---

### Audit 1 — COGS Accuracy

**Question:** Does the formula COGS (derived from stock movements) agree with the COGS posted to the General Ledger?

**How to check:**

1. Run **Audit Trading Account Report** for the company and period.
2. Locate the **COGS Variance** row in the GL Reconciliation section.
3. If ✅ (zero): formula COGS equals GL COGS — no discrepancy to investigate.
4. If ❌ (non-zero): open **Item COGS Analysis** for the same period.
5. Sort the **COGS Diff** column descending — items with the largest SLE-vs-GL gap appear at the top.
6. The sum of COGS Diff across all items should equal the COGS Variance in the Trading Account.
7. For each offending item, open **Stock Ledger** filtered to that item to find the specific voucher where SLE and GL diverge.

**Common causes of COGS Variance:**

| Cause | How it appears |
|---|---|
| Perpetual Inventory not enabled | All items show COGS Diff = Sales COGS (GL COGS is 0 everywhere) |
| LCV posted after delivery | SLE valuation updated retroactively; GL COGS still at original rate |
| Manual GL entry on COGS account | GL COGS inflated or deflated with no SLE counterpart |
| Delivery backdated past a valuation change | Rate used in GL differs from rate now in SLE |

---

### Audit 2 — Stock Balance Integrity

**Question:** Does the live stock value in the system (tabBin) agree with the GL stock account balance?

**How to check:**

1. Run **Audit Trading Account Report**.
2. Locate the **Bin vs Stock Account GL** row.
3. If ✅ (zero): inventory records and the balance sheet are in agreement.
4. If ❌ (non-zero): the discrepancy is the difference between physical stock value and what is recorded in the GL.
5. Open the **GL Entry** report filtered to the stock accounts for the period.
6. Look for entries where the `voucher_type` is not a standard inventory transaction (no corresponding SLE), or for entries marked cancelled that were not reversed.
7. The unmatched GL entry is the source of the difference.

**Common causes of Bin vs GL discrepancy:**

| Cause | How it appears |
|---|---|
| Voucher cancelled without GL reversal | GL balance reduces; Bin stays the same |
| Direct journal entry to stock account | GL balance changes with no SLE |
| Perpetual inventory enabled mid-year with no opening entry | GL opens at zero; Bin holds the prior balance |
| Purchase Receipt cancelled after Payment | Bin reduced; AP side may prevent GL reversal |

---

### Audit 3 — Stock Equation per Item

**Question:** Does each item's stock movement equation balance to zero?

**How to check:**

1. Run **Item COGS Analysis Report** for the company and period.
2. Scan the **Variance** column — all items should show ✓ green.
3. Any item showing ⚠ red has an unbalanced SLE. The equation is:
   ```
   Opening + Inflows − Outflows − Closing = Variance
   ```
4. For the flagged item, open **Stock Ledger** and filter to that item and period.
5. Find the entry where the SLE row exists without a matching reverse — this is typically a partially-cancelled document.

**Common causes of non-zero Variance:**

| Cause | Effect |
|---|---|
| Partially cancelled Stock Entry | One SLE row removed, the other remains |
| Purchase Receipt cancelled after LCV | LCV rows remain, PR rows removed |
| Return not linked to original document | Duplicate stock reduction or increase |

---

### Audit 4 — Period Continuity

**Question:** Does the opening stock of this period equal the closing stock of the previous period?

**How to check:**

1. Run **Audit Trading Account Report** (or Item COGS Analysis) for period N.
2. Note the **Closing Stock** value.
3. Run the same report for period N+1.
4. The **Opening Stock** must equal Closing Stock of period N exactly.
5. Any difference means a backdated entry was posted in the gap — a transaction was dated inside period N after that period was reviewed.

**To prevent backdating:** Post a Period Closing Voucher in ERPNext after sign-off to lock the period against further entries.

---

### Audit 5 — Purchase Verification

**Question:** Are purchases correctly classified and supported by source documents?

**How to check using Item COGS Analysis:**

| Column | Verification step |
|---|---|
| Local PR | Total should match Purchase Receipt report filtered to company default currency for the period |
| Import PR | Total should match Purchase Receipt report filtered to foreign currency. Each import PR should have a corresponding LCV |
| LCV | Verify posting date is in the same period as the related Purchase Receipt. LCV posted in a later period inflates that period's COGS |
| PI Rate Adj | Large negative values indicate supplier invoices consistently below receipt valuations — verify with supplier price agreements |
| Pur Returns | Each return should be linked to the original Purchase Receipt. Unlinked returns misstate Opening Stock in subsequent periods |

---

### Audit 6 — Sales Return Integrity

**Question:** Are sales returns correctly recorded and linked to original invoices?

**How to check:**

1. In **Item COGS Analysis**, review the **Sales Ret In** column.
2. Unexpected values (large or for items with no sales in the period) indicate a return against a prior-period invoice or an unlinked return.
3. Open each flagged sales return document and verify:
   - It references the original Sales Invoice or Delivery Note
   - The stock value used for the return matches the original delivery rate
4. Unlinked or mispriced returns inflate closing stock and understate COGS.

---

### Audit 7 — Warehouse Transfer Completeness

**Question:** Do inter-warehouse transfers balance across the company?

**How to check:**

1. Run **Item COGS Analysis** without a Warehouse filter (company-wide).
2. In the TOTAL row, **Transfer In** must equal **Transfer Out**.
3. If they differ, a transfer was partially cancelled, or one leg of the transfer was posted to a warehouse outside the current filter.
4. Remove all warehouse filters and re-run to confirm both legs are visible.
5. Per-item imbalance indicates a transfer was posted for the item in one direction only.

---

### Period-End Sign-Off Sequence

Run these steps in order at the close of each period:

| Step | Action | Report | Pass Condition |
|---|---|---|---|
| 1 | Verify COGS Variance | Audit Trading Account | COGS Variance = 0 ✅ |
| 2 | Verify Bin vs GL | Audit Trading Account | Bin vs Stock GL = 0 ✅ |
| 3 | Check Gross Margin % | Audit Trading Account | Within expected range vs prior period |
| 4 | Verify item-level stock equations | Item COGS Analysis | All Variance = 0 ✅ |
| 5 | Verify item-level COGS | Item COGS Analysis | All COGS Diff = 0 ✅ |
| 6 | Verify Transfer balance | Item COGS Analysis (no WH filter) | Transfer In = Transfer Out in TOTAL row |
| 7 | Verify period continuity | Both reports | Opening this period = Closing prior period |
| 8 | Verify purchase totals | Item COGS Analysis | Local PR + Import PR totals tie to Purchase Receipt report; PI Rate Adj ties to Purchase Invoices |
| 9 | Post Period Closing Voucher | ERPNext | Period locked against backdated entries |
| 10 | Archive report outputs | — | PDFs saved with working papers |

If any step fails, the Audit Guide at `/app/audit-guide` provides the cause and remediation action for each check.

---

## Technical Notes

### SQL Parameter Order

The Item COGS Analysis query separates `select_params` (CASE WHEN date range comparisons, 23 parameters) from `where_params` (WHERE clause filters). This prevents MySQL from binding the company name string to a date-comparison placeholder, which would silently return zero rows.

### Module Path

Reports and the guide page are under `periodic_accounting/periodic_accounting/periodic_accounting/`. Frappe's `get_module_path("Periodic Accounting")` resolves this for both report execution and page JS serving.

### Page Sync

An `after_migrate` hook in `install.py` force-imports each page JSON in the `page/` directory. The guide page stays in sync with the database on every `bench migrate`.

### Scheduler

A cron entry (`30 23 28-31 * *`) triggers `tasks.auto_periodic_accounting_entry` on the last day of each month.

---

## Related Files

| File | Purpose |
|---|---|
| `PERIODIC_ACCOUNTING.md` | Setup guide and worked accounting example for the Periodic Accounting Entry |
| `periodic_accounting/install.py` | `after_migrate` / `after_install` hooks |
| `periodic_accounting/hooks.py` | App hooks, scheduler events |
| `periodic_accounting/tasks.py` | Monthly auto-posting task |
| `periodic_accounting/periodic_accounting/report/audit_trading_account_report/` | Audit Trading Account scripts |
| `periodic_accounting/periodic_accounting/report/item_cogs_analysis_report/` | Item COGS Analysis scripts |
| `periodic_accounting/periodic_accounting/page/audit_guide/` | Audit Guide page |
