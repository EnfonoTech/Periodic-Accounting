# Periodic Accounting — User Guide

This app provides two features for companies running **Periodic Inventory** in ERPNext:

1. **Periodic Stock Reconciliation (PSR)** — month-end voucher to recognise closing stock on the Balance Sheet and correct COGS.
2. **Realtime Trading Account Report** — live P&L-style trading account with drill-down links to source registers.

---

## 1. Prerequisites & Setup

### 1.1 Company Setting — Disable Perpetual Inventory

Go to: **Setup → Company → [Your Company]**

- Uncheck **"Enable Perpetual Inventory"**
- Save

> This switches ERPNext to Periodic Inventory mode. Stock movements (Purchase Receipt, Delivery Note) will update `tabBin` only — **no GL entries are posted for stock movements**.

### 1.2 Chart of Accounts — Stock Adjustment Account

Create a leaf account under your COGS group:

| Field | Value |
|---|---|
| Account Name | Stock Adjustment |
| Account Number | *(e.g. 51010600001)* |
| Parent Account | *(your COGS group, e.g. 5101 - COGS)* |
| Account Type | **Cost of Goods Sold** |
| Root Type | Expense |
| Is Group | No |

This account is used as the **Difference Account** on every PSR. The JE credits this account (reducing net COGS) when closing stock is recognised.

### 1.3 Stock Accounts on Warehouse Master *(only if you have multiple stock accounts)*

If your Chart of Accounts has more than one Stock-type account (e.g. *Trading Inventory* and *Stock In Transit*), each warehouse must be linked to the correct account:

Go to: **Stock → Warehouse → [Warehouse Name]**

- Set **Account** field → select the stock account this warehouse feeds into

ERPNext's `get_stock_and_account_balance` uses this mapping to compute the correct bin value per stock account. If left blank, all warehouses are summed against every stock account (double-counting).

### 1.4 Cost Center on Warehouse Master *(optional — for P&L by branch)*

If you want the PSR Journal Entry to carry a cost center (so the closing stock entry appears in the correct branch P&L):

Go to: **Stock → Warehouse → [Warehouse Name]**

- Set **Cost Center** field

Then, on the PSR form, set the **Cost Center** field before clicking Get Balance — it will be stamped on all JE rows.

### 1.5 Item Setup

- `Is Stock Item` must be checked on the item
- Set default warehouse, expense account, and cost center under **Item Defaults** for the company

---

## 2. How Periodic Inventory Works (Accounting Logic)

In periodic inventory, **stock accounts are not touched by day-to-day transactions**. COGS is recognised at point-of-purchase, not point-of-sale.

| Transaction | GL Effect | Stock (tabBin) |
|---|---|---|
| Purchase Receipt | None | Qty increases |
| Purchase Invoice | Dr COGS / Cr Accounts Payable | Qty increases (if `update_stock=1`) |
| Sales Invoice (update_stock=1) | Dr AR / Cr Sales Revenue | Qty decreases |
| Delivery Note | None | Qty decreases |
| **PSR (month-end)** | **Dr Trading Inventory / Cr Stock Adjustment** | No change |

The PSR corrects the over-stated COGS: all purchases hit COGS immediately, but the closing stock (goods still on hand) must be recognised as an asset and removed from COGS expense.

---

## 3. Test Entry Flow

Use the following sequence to verify the feature end-to-end.

**Assumptions:**
- Company: SF Trading (currency BHD)
- Item: Pencil (stock item, no batch/serial)
- Purchase price: BHD 25/unit | Selling price: BHD 40/unit
- Warehouse: Stores - ST | Expense account: Local Purchases - ST
- Opening stock: 0 units

---

### Step 1 — Purchase Receipt *(optional)*

> Creates stock only. No GL entry in periodic mode.

**Document:** Purchase Receipt
| Field | Value |
|---|---|
| Supplier | *(any)* |
| Item | Pencil |
| Qty | 10 |
| Rate | 25 |
| Warehouse | Stores - ST |

**Result after save/submit:**
- tabBin: Pencil @ Stores — 10 units @ BHD 25 = **BHD 250**
- GL: no entry

---

### Step 2 — Purchase Invoice

> Posts the COGS entry. If `update_stock=1`, also moves stock (skip Step 1 then).

**Document:** Purchase Invoice
| Field | Value |
|---|---|
| Supplier | *(any)* |
| Update Stock | ✓ (if no separate Purchase Receipt) |
| Item | Pencil |
| Qty | 10 |
| Rate | 25 |
| Expense Account | Local Purchases - ST |

**GL entries posted:**
```
Dr  Local Purchases (COGS)    BHD 250
Cr  Accounts Payable          BHD 250
```

**tabBin:** 10 units @ BHD 25 = BHD 250

---

### Step 3 — Sales Invoice (with Update Stock)

> Records revenue and reduces stock.

**Document:** Sales Invoice
| Field | Value |
|---|---|
| Customer | *(any)* |
| Update Stock | ✓ |
| Item | Pencil |
| Qty | 4 |
| Rate | 40 |
| Warehouse | Stores - ST |

**GL entries posted:**
```
Dr  Accounts Receivable    BHD 160
Cr  Sales Revenue          BHD 160
```

**tabBin:** 6 units @ BHD 25 = **BHD 150** *(4 units sold)*

---

### Step 4 — Periodic Stock Reconciliation

> Month-end entry to recognise closing stock as an asset and reduce COGS.

**Document:** Periodic Accounting → Periodic Stock Reconciliation → New

| Field | Value |
|---|---|
| Company | SF Trading |
| Posting Date | Last day of month |
| For All Stock Accounts | ✓ |
| Cost Center | *(optional — for branch P&L)* |
| Difference Account | Stock Adjustment - ST |

Click **Get Balance**.

The system computes per stock account:
- `stock_bal` = BHD 150 (from tabBin)
- `account_bal` = BHD 0 (Trading Inventory GL has no prior entries)
- Difference = **BHD 150**

**Accounts table populated:**
| Account | Dr | Cr |
|---|---|---|
| Trading Inventory - ST | 150 | |
| Stock Adjustment - ST | | 150 |

**Submit** → Journal Entry auto-created and linked.

**JE posted:**
```
Dr  Trading Inventory (BS Asset)    BHD 150
Cr  Stock Adjustment (COGS)         BHD 150
```

---

### Next Month — Incremental Reconciliation

In Month 2, suppose 2 more units purchased (BHD 50) and 3 units sold:
- tabBin closing = 5 units @ BHD 25 = BHD 125
- Trading Inventory GL balance = BHD 150 (from Month 1 PSR)
- Difference = 125 − 150 = **−BHD 25** (stock reduced)

**JE posted:**
```
Cr  Trading Inventory (BS Asset)    BHD 25
Dr  Stock Adjustment (COGS)         BHD 25
```

The PSR always reconciles to the *current* tabBin value, incrementally.

---

## 4. GL / Ledger Reflection

### After all steps above, the General Ledger shows:

| Account | Dr | Cr | Net |
|---|---|---|---|
| Local Purchases (COGS) | 250 | — | 250 Dr |
| Accounts Payable | — | 250 | 250 Cr |
| Accounts Receivable | 160 | — | 160 Dr |
| Sales Revenue | — | 160 | 160 Cr |
| Trading Inventory (BS) | 150 | — | 150 Dr |
| Stock Adjustment (COGS) | — | 150 | 150 Cr |

**Net COGS on the P&L:**
```
Local Purchases     +250
Stock Adjustment    −150
──────────────────────────
Net COGS             100
```

---

## 5. Realtime Trading Account Report

**Path:** Accounts → Reports → Realtime Trading Account Report

**Filters:**

| Filter | Description |
|---|---|
| Company | Required |
| From Date | Period start (defaults to month start) |
| To Date | Period end (defaults to today) |
| Warehouse | Optional — narrow stock figures to one warehouse |

**How each row is computed:**

| Row | Source |
|---|---|
| Gross Sales Revenue | GL credits on Income accounts from SI/DN |
| Less: Sales Returns | GL debits on Income accounts from SI/DN |
| Opening Stock | Cumulative SLE `stock_value_difference` before `from_date` |
| Add: Gross Purchases | GL debits on COGS accounts from PI/PR |
| Less: Purchase Returns | GL credits on COGS accounts from PI/PR |
| Less: Closing Stock (Live) | tabBin (if `to_date` ≥ today) or cumulative SLE |
| COGS | Opening + Net Purchases − Closing |
| Gross Profit | Net Sales − COGS |

**Drill-down links:**

| Row | Clicks through to |
|---|---|
| Sales rows | Sales Register |
| Purchase rows | Purchase Register |
| Opening / Closing Stock | Stock Balance report |

**Result with test data above:**
```
SALES
  Gross Sales Revenue          160 Cr
  Less: Sales Returns            0
Net Sales Revenue              160 Cr

COST OF SALES
  Opening Stock                  0
  Add: Gross Purchases         250 Dr
  Net Purchases                250 Dr

  Goods Available for Sale     250
  Less: Closing Stock (Live)   150 Cr

COST OF GOODS SOLD             100 Dr

GROSS PROFIT                    60 Cr
```

> The report uses **live tabBin** for closing stock (not the PSR JE), so it reflects real-time stock value even before the month-end PSR is posted. This is by design — the trading account is always current.

---

## 6. Standard P&L Report (ERPNext)

**Path:** Accounts → Reports → Profit and Loss Statement

After the PSR JE is submitted, the standard ERPNext P&L correctly shows:

```
Income
  Sales Revenue                 160

Expense (COGS group)
  Local Purchases               250
  Stock Adjustment             (150)   ← PSR credit reduces COGS
  ─────────────────────────────────
  Net COGS                      100

Gross Profit                     60
```

**Before PSR is submitted**, the P&L will show COGS = 250 (over-stated) because closing stock has not yet been recognised. This is expected in periodic inventory — the PSR is the month-end correction entry.

### P&L by Cost Center

If Cost Center is set on the PSR:
1. The JE rows carry the cost center
2. In **Profit and Loss Statement**, set the **Cost Center** filter
3. The Stock Adjustment credit will appear under the correct branch, giving an accurate branch-level GP

---

## 7. Summary of Key Rules

| Rule | Detail |
|---|---|
| PSR only for periodic companies | Controller rejects if `enable_perpetual_inventory = 1` |
| Difference Account must be COGS type | Filtered in the form to `account_type = Cost of Goods Sold` |
| Multiple stock accounts | Set `account` on each Warehouse master; ERPNext splits automatically |
| Amend support | PSR is submittable; amend cancels the linked JE and recreates |
| Scheduler | `auto_periodic_stock_reconciliation` runs on last day of month at 23:30 for all periodic companies |
