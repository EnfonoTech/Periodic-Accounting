# Periodic Accounting

An ERPNext app that provides audit-grade reporting for inventory-heavy businesses running perpetual inventory accounting. It delivers the periodic accounting perspective — formula-based COGS derivation and stock reconciliation — as a verification layer on top of ERPNext's automated GL postings.

---

## Why This Exists

In ERPNext perpetual inventory, every stock movement automatically posts a GL entry. The expectation is that auditors trust the automated COGS postings. In practice, they don't — and rightly so. Manual journals, cancellation errors, and misconfigured accounts can silently distort the GL without triggering any system alert.

Auditors are trained to independently derive COGS using the periodic accounting formula:

```
Opening Stock
+ Purchases  (Local + Import + Landed Costs + Rate Adjustments)
− Purchase Returns
= Goods Available for Sale
− Closing Stock
─────────────────────────
= Cost of Goods Sold
```

No standard ERPNext report produces this derivation and compares it to the GL in one view. This app does.

---

## Reports

### Audit Trading Account Report

Reconstructs the full trading account from the Stock Ledger Entry — entirely independent of the GL — and places it alongside the GL figures for direct comparison.

| What an auditor derives in periodic accounting | What this report provides |
|---|---|
| Opening stock value | Opening (SLE cumulative before period start) |
| Purchases by type | Local PR, Import PR, LCV, PI Rate Adjustment |
| Purchase returns | Purchase Returns |
| Closing stock | Closing (live Bin or historical SLE cumulative) |
| Formula COGS | Opening + Net Purchases − Closing |
| Reported COGS | GL debit−credit on Cost of Goods Sold accounts |
| Discrepancy | COGS Variance = Formula COGS − GL COGS |
| Stock account accuracy | Bin Value vs GL Stock Account Balance |

**Key checks the report runs automatically:**
- **COGS Variance** — Formula COGS minus GL COGS. Must be zero. Non-zero means a cancelled document, manual journal, or SLE/GL mismatch.
- **Bin vs GL** — Live stock value (Bin) minus the all-time GL stock account balance. Must be zero. Non-zero means a direct journal was posted to a stock account, or a GL auto-entry failed.

Purchase split columns (Local PR, Import PR, LCV, PI Rate Adj) trace each line to a specific source document type, allowing independent cross-check against Purchase Receipt report, Landed Cost Vouchers, and Purchase Invoices separately.

---

### Item COGS Analysis Report

Runs the same periodic accounting verification at item level. Every item gets a row. The Variance column enforces:

```
Opening + All Inflows − All Outflows − Closing = 0
```

| Column | Source |
|---|---|
| Opening | SLE cumulative before period |
| Local PR / Import PR | Purchase Receipt SLEs by currency |
| LCV | Landed Cost Voucher SLEs |
| PI Rate Adj | Purchase Invoice SLEs |
| Pur Returns | Negative svd from PR/PI returns |
| Transfer In / Out | Material Transfer Stock Entry |
| Mfg / Issue Out | Material Issue, Manufacture, and other outflows |
| Sales COGS | Sales Invoice / Delivery Note outflows |
| Sales Ret In | Sales return inflows |
| Closing | Live Bin or historical SLE cumulative |
| **Variance** | Must be zero for every item |
| GL COGS | GL debit−credit on COGS accounts for this item |
| **COGS Diff** | Sales COGS (SLE) − GL COGS; must be zero |

A non-zero Variance flags an unbalanced or cancelled transaction for that specific item. COGS Diff non-zero means the perpetual COGS posting for that item did not match the stock movement.

---

## How These Reports Stand Out

### Built from Stock Ledger, Not GL

Formula COGS is derived from `tabStock Ledger Entry`, which can only be written by system documents — not manual journals. This makes it immune to GL-level manipulation. Any manual journal posted to a COGS or stock account shows up immediately as a variance.

### Both Sources in One View

Standard ERPNext reports see either the stock ledger or the GL, never both:

| Standard Report | What it shows | What it misses |
|---|---|---|
| Stock Ledger | SLE movements | No GL comparison |
| Trial Balance | GL balances | No stock movement breakdown |
| Purchase Register | Purchase Invoices only | Misses PRs and LCVs |
| Stock Balance | Closing qty/value | No movement reconciliation |
| Gross Profit | GL-derived COGS | No SLE-based verification |

These reports sit at the intersection and are the only place where the full perpetual cycle — receipt → cost layering → delivery → COGS posting → stock account — is verified end to end.

### Periodic Formula as a Perpetual Check

The periodic accounting formula has been used by auditors for decades because it is document-driven and independently verifiable. These reports apply that same formula inside a live perpetual system, giving auditors the output they are trained to verify while the business retains the benefits of real-time stock accounting.

---

## Other Features

- **Periodic Accounting Entry** — Creates closing stock adjustment journal entries at period end, with configurable accounts and cost centres.
- **Stock Ledger Report** — Filtered stock movement view with voucher-type breakdown.
- **Automated Scheduling** — Month-end periodic entries can be scheduled via the built-in cron hook.

---

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app periodic_accounting
```

After installation, run `bench migrate` to sync all pages and reports.

---

## License

MIT
