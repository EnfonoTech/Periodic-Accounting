# Periodic Accounting — User Guide

This app provides two features for companies running **Periodic Inventory** in ERPNext:

1. **Periodic Accounting Entry (PAE)** — month-end voucher to recognise closing stock on the Balance Sheet and correct COGS.
2. **Realtime Trading Account Report** — live P&L-style trading account with drill-down links to source registers.

---

## 1. Prerequisites & Setup

### 1.1 Company Setting — Disable Perpetual Inventory

Go to: **Setup → Company → [Your Company]**

- Uncheck **"Enable Perpetual Inventory"**
- Save

> This switches ERPNext to Periodic Inventory mode. Stock movements (Purchase Receipt, Delivery Note) update `tabBin` only — **no GL entries are posted for stock movements**.

### 1.2 Chart of Accounts — Periodic Entry Difference Account

Create a leaf account under your COGS group:

| Field | Value |
|---|---|
| Account Name | Periodic Entry Difference Account |
| Account Number | *(e.g. 51010600001)* |
| Parent Account | *(your COGS group, e.g. 5101 - COGS)* |
| Account Type | **Cost of Goods Sold** |
| Root Type | Expense |
| Is Group | No |

This account is used as the **Difference Account** on every PAE. The JE credits this account (reducing net COGS) when closing stock is recognised.

### 1.3 Stock Account on Warehouse Master *(required only if multiple stock accounts)*

If your Chart of Accounts has more than one Stock-type account (e.g. *Trading Inventory* and *Stock In Transit*), each warehouse must be linked to the correct account so ERPNext can split stock values correctly:

Go to: **Stock → Warehouse → [Warehouse Name]** → set the **Account** field.

ERPNext's `get_stock_and_account_balance` uses this mapping to compute the correct bin value per stock account when "For All Stock Accounts" is ticked. If left blank on a multi-account COA, all warehouses are summed against every stock account (double-counting).

> If the company has only **one** stock account, no warehouse-to-account mapping is needed — all company warehouse balances are summed automatically.

### 1.4 Cost Center on PAE *(optional — for P&L attribution)*

The **Cost Center** field on the PAE form is purely an attribution tag. When set, it is stamped on every Journal Entry row so the Periodic Entry Difference Account credit appears under that cost center in the standard P&L report.

**Important:** this field does **not** filter which warehouses are included in the stock balance calculation. The stock balance always covers all warehouses linked to the stock account (or all company warehouses if only one account exists). The cost center is only for GL tagging.

To accurately split a closing stock entry across two branches, set up a **separate stock account per branch** (via the Warehouse → Account mapping in 1.3), then run one PAE per account.

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
| **PAE (month-end)** | **Dr Trading Inventory / Cr Periodic Entry Difference Account** | No change |

The PAE corrects over-stated COGS: all purchases hit COGS immediately, but closing stock (goods still on hand) must be recognised as a Balance Sheet asset and removed from COGS.

---

## 3. Test Entry Flow

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
| Item | Pencil, Qty 10, Rate 25 |
| Warehouse | Stores - ST |

**Result:** tabBin — 10 units @ BHD 25 = **BHD 250** | GL — no entry

---

### Step 2 — Purchase Invoice

> Posts the COGS entry. Set `update_stock=1` if skipping Step 1.

**Document:** Purchase Invoice
| Field | Value |
|---|---|
| Supplier | *(any)* |
| Update Stock | ✓ (if no separate Purchase Receipt) |
| Item | Pencil, Qty 10, Rate 25 |
| Expense Account | Local Purchases - ST |

**GL entries posted:**
```
Dr  Local Purchases (COGS)    BHD 250
Cr  Accounts Payable          BHD 250
```

---

### Step 3 — Sales Invoice (with Update Stock)

**Document:** Sales Invoice
| Field | Value |
|---|---|
| Customer | *(any)* |
| Update Stock | ✓ |
| Item | Pencil, Qty 4, Rate 40 |
| Warehouse | Stores - ST |

**GL entries posted:**
```
Dr  Accounts Receivable    BHD 160
Cr  Sales Revenue          BHD 160
```

**tabBin after:** 6 units @ BHD 25 = **BHD 150**

---

### Step 4 — Periodic Accounting Entry

**Path:** Periodic Accounting → Periodic Accounting Entry → New

| Field | Value |
|---|---|
| Company | SF Trading |
| Posting Date | Last day of month |
| For All Stock Accounts | ✓ |
| Cost Center | *(optional)* |
| Difference Account | Periodic Entry Difference Account - ST |

Click **Get Balance**. The system computes per stock account:
- `stock_bal` = BHD 150 (tabBin)
- `account_bal` = BHD 0 (no prior PAE)
- Difference = **BHD 150**

**Accounts table populated:**

| Account | Dr | Cr |
|---|---|---|
| Trading Inventory - ST | 150 | |
| Periodic Entry Difference Account - ST | | 150 |

**Submit** → Journal Entry auto-created and linked.

**JE posted:**
```
Dr  Trading Inventory (BS Asset)              BHD 150
Cr  Periodic Entry Difference Account (COGS)  BHD 150
```

---

### Next Month — Incremental Reconciliation

Suppose 2 more units purchased (BHD 50) and 3 units sold:
- tabBin closing = 5 units @ BHD 25 = BHD 125
- Trading Inventory GL balance = BHD 150 (from Month 1 PAE)
- Difference = 125 − 150 = **−BHD 25**

**JE posted:**
```
Cr  Trading Inventory (BS Asset)              BHD 25
Dr  Periodic Entry Difference Account (COGS)  BHD 25
```

The PAE always reconciles to the current tabBin value, incrementally.

---

## 4. GL / Ledger Reflection

After all steps above:

| Account | Dr | Cr | Net |
|---|---|---|---|
| Local Purchases (COGS) | 250 | — | 250 Dr |
| Accounts Payable | — | 250 | 250 Cr |
| Accounts Receivable | 160 | — | 160 Dr |
| Sales Revenue | — | 160 | 160 Cr |
| Trading Inventory (BS) | 150 | — | 150 Dr |
| Periodic Entry Difference Account (COGS) | — | 150 | 150 Cr |

**Net COGS on the P&L:**
```
Local Purchases                        +250
Periodic Entry Difference Account      −150
──────────────────────────────────────────
Net COGS                                100
```

---

## 5. Realtime Trading Account Report

**Path:** Accounts → Reports → Realtime Trading Account Report

**Filters:** Company (req), From Date, To Date, Warehouse (optional)

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

**Drill-down links:** Sales rows → Sales Register | Purchase rows → Purchase Register | Stock rows → Stock Balance

> The report uses **live tabBin** for closing stock, not the PAE JE, so it reflects real-time stock value even before the month-end entry is posted.

**Expected output with test data:**
```
SALES
  Gross Sales Revenue          160 Cr
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

---

## 6. Standard P&L Report (ERPNext)

**Path:** Accounts → Reports → Profit and Loss Statement

After the PAE JE is submitted:

```
Income
  Sales Revenue                              160

Expense (COGS group)
  Local Purchases                            250
  Periodic Entry Difference Account         (150)   ← PAE credit reduces COGS
  ──────────────────────────────────────────────
  Net COGS                                   100

Gross Profit                                  60
```

**Before PAE is submitted**, P&L shows COGS = 250 (over-stated). This is expected — the PAE is the month-end correction.

**P&L by Cost Center:** If Cost Center is set on the PAE, the Periodic Entry Difference Account JE rows carry that cost center. Filter the P&L report by that cost center to see the closing stock credit attributed to the correct branch. Note that the stock balance calculation itself is not filtered by cost center — only the GL tagging is. For a proper per-branch split, use separate stock accounts per warehouse (Section 1.3).

---

## 7. Summary of Key Rules

| Rule | Detail |
|---|---|
| PAE only for periodic companies | Controller rejects if `enable_perpetual_inventory = 1` |
| Difference Account must be COGS type | Form filter enforces `account_type = Cost of Goods Sold` |
| Multiple stock accounts | Set `account` on each Warehouse master; ERPNext splits automatically |
| Amend support | PAE is submittable; amend cancels the linked JE and recreates |
| Scheduler | `auto_periodic_accounting_entry` runs on last day of month at 23:30 for all periodic companies |
