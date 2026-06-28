# Periodic Accounting — User Guide

This app provides two features for companies running **Periodic Inventory** in ERPNext:

1. **Periodic Accounting Entry (PAE)** — period-end voucher to recognise closing stock on the Balance Sheet and implicitly determine COGS through the Trading Account structure.
2. **Realtime Trading Account Report** — live P&L-style trading account with drill-down links to source registers.

---

## 1. Prerequisites & Setup

### 1.1 Company Setting — Disable Perpetual Inventory

Go to: **Setup → Company → [Your Company]**

- Uncheck **"Enable Perpetual Inventory"**
- Save

> This switches ERPNext to Periodic Inventory mode. Stock movements (Purchase Receipt, Delivery Note, Purchase Invoice) update `tabBin` only — **no automatic GL entries are posted for stock movements**. Inventory and the accounting ledger are deliberately kept out of sync until you post the period-end PAE.

### 1.2 Chart of Accounts — Two Accounts Required

You need exactly two accounts for the periodic accounting entries:

**Account A — Stock-in-Hand (Balance Sheet)**

| Field | Value |
|---|---|
| Account Name | Stock-in-Hand |
| Parent Account | *(your Current Assets group)* |
| Account Type | Stock |
| Root Type | Asset |
| Is Group | No |

This account holds the **recognised closing stock value**. Its balance equals the closing stock posted by the most recent PAE. It is the opening stock figure for the next period. Purchases must **never** be posted to this account.

**Account B — Closing Stock (Income Statement)**

| Field | Value |
|---|---|
| Account Name | Closing Stock (Income Statement) |
| Parent Account | *(your Direct Income or Trading Income group)* |
| Account Type | Income Account |
| Root Type | Income |
| Is Group | No |

This account is credited when closing stock increases (stock in) and debited when it decreases (stock out). It appears on the credit side of the Trading Account, reducing net COGS. Its year-end balance is closed to Retained Earnings as part of normal financial year closing.

### 1.3 Purchase Accounts — Purchases Flow to Expense, NOT to Stock-in-Hand

In periodic accounting, **stock is not recognised as an asset when purchased**. Purchases are expensed immediately and the Stock-in-Hand asset is only recognised at period-end via the PAE.

Set the **Expense Account** on every item (or item default) to a **Purchases** expense account:

| Field | Value |
|---|---|
| Account Name | Purchases |
| Parent Account | *(your Direct Expenses / COGS group)* |
| Account Type | *(leave blank or use Expense Account)* |
| Root Type | Expense |

> If you accidentally route Purchase Invoices to the Stock-in-Hand (Asset) account, the PAE will compute a wrong figure — the GL will already contain the purchase value, and the tabBin comparison will show COGS instead of closing stock.

### 1.4 Warehouse → Stock Account Mapping *(multi-account setups only)*

If your COA has more than one Stock-type Asset account, link each warehouse to the correct account:

Go to: **Stock → Warehouse → [Warehouse Name]** → set the **Account** field.

ERPNext's `get_stock_and_account_balance` uses this mapping to split bin values per stock account. If only one stock account exists, all warehouse bins are summed automatically — no mapping needed.

### 1.5 Cost Center on PAE *(optional)*

The **Cost Center** field on the PAE is an attribution tag stamped on every JE row. It does not filter which warehouses are included in the calculation.

---

## 2. How Periodic Inventory Works (Accounting Logic)

Inventory and the accounting ledger are **not automatically synced**. Purchases are posted to a Purchases expense account and stock quantities are tracked in `tabBin` only. The Stock-in-Hand asset on the Balance Sheet is zero (or last period's closing value) until you manually post the PAE.

At period-end, you compare **opening stock** (the current Stock-in-Hand GL balance, which is last period's closing stock) with **closing stock** (current physical count / `tabBin` value) and post the net change.

| Transaction | GL Effect | Stock (tabBin) |
|---|---|---|
| Purchase Receipt | None | Qty / value increases |
| Purchase Invoice | Dr **Purchases (Expense)** / Cr Accounts Payable | Qty / value increases (if `update_stock=1`) |
| Sales Invoice (update_stock=1) | Dr AR / Cr Sales Revenue | Qty / value decreases |
| Delivery Note | None | Qty / value decreases |
| **PAE (period-end)** | **Dr Stock-in-Hand (BS) / Cr Closing Stock IS** *(net change)* | No change |

### Journal Entry Logic

The PAE computes: **net change = tabBin closing value − Stock-in-Hand GL balance**

| Scenario | Meaning | PAE Entry |
|---|---|---|
| net change > 0 | Closing stock > Opening stock (net purchases > net sales) | Dr Stock-in-Hand (BS) / Cr Closing Stock IS |
| net change < 0 | Closing stock < Opening stock (net sales consumed more than purchased) | Dr Closing Stock IS / Cr Stock-in-Hand (BS) |
| net change = 0 | No movement | No entry needed |

### COGS Recognition

COGS is never posted to its own GL account directly. It is derived implicitly on the Trading Account:

```
COGS = Opening Stock + Purchases − Closing Stock
     = Stock-in-Hand (opening GL) + Purchases (expense) − Closing Stock IS (income credit)
```

The standard ERPNext P&L will show:

```
INCOME
  Sales Revenue                    xxx Cr
  Closing Stock (Income Statement) xxx Cr  ← PAE credit (closing stock recognised)

DIRECT EXPENSES
  Purchases                        xxx Dr  ← Purchase Invoices
```

Opening stock is implicitly the reduction in the Stock-in-Hand (BS) asset that occurs when the PAE's net change is negative; it does not appear as a separate P&L line unless you use the Realtime Trading Account Report.

---

## 3. Test Entry Flow

**Assumptions:**
- Company: SF Trading (currency BHD)
- Item: Pencil (stock item, no batch/serial)
- Purchase price: BHD 25/unit | Selling price: BHD 40/unit
- Warehouse: Stores - ST
- Expense account on item: **Purchases - ST** *(Direct Expense type)*
- Opening Stock-in-Hand: 0 (start of business)

---

### Step 1 — Purchase Receipt *(optional)*

> Creates stock only. No GL entry in periodic mode.

**Document:** Purchase Receipt — Pencil, Qty 10, Rate 25, Warehouse: Stores - ST

**Result:** tabBin = 10 units @ BHD 25 = **BHD 250** | GL = no entry

---

### Step 2 — Purchase Invoice

> Posts to the **Purchases (Expense)** account — Stock-in-Hand is not touched.

**Document:** Purchase Invoice
| Field | Value |
|---|---|
| Supplier | *(any)* |
| Update Stock | ✓ (if no separate Purchase Receipt) |
| Item | Pencil, Qty 10, Rate 25 |
| Expense Account | **Purchases - ST** *(Expense, NOT Stock-in-Hand)* |

**GL entries posted:**
```
Dr  Purchases (Expense)     BHD 250
Cr  Accounts Payable        BHD 250
```

Stock-in-Hand GL balance: **0** | tabBin: **BHD 250**

---

### Step 3 — Sales Invoice (with Update Stock)

**Document:** Sales Invoice — Pencil, Qty 4, Rate 40, Update Stock ✓

**GL entries posted:**
```
Dr  Accounts Receivable    BHD 160
Cr  Sales Revenue          BHD 160
```

**tabBin after:** 6 units @ BHD 25 = **BHD 150** | Stock-in-Hand GL: **0**

---

### Step 4 — Periodic Accounting Entry

**Path:** Periodic Accounting → Periodic Accounting Entry → New

| Field | Value |
|---|---|
| Company | SF Trading |
| Posting Date | Last day of period |
| For All Stock Accounts | ✓ |
| Closing Stock Account (IS) | Closing Stock (Income Statement) - ST |

Click **Get Balance**. The system computes per stock account:

- `account_bal` (Stock-in-Hand GL) = **BHD 0** ← opening stock, only updated by PAE
- `stock_bal` (tabBin) = **BHD 150** ← current physical closing stock
- Net change = 150 − 0 = **+BHD 150** (closing > opening → stock in)

**Accounts table populated:**

| Account | Dr | Cr |
|---|---|---|
| Stock-in-Hand - ST | 150 | |
| Closing Stock (Income Statement) - ST | | 150 |

**Submit** → Journal Entry auto-created and linked.

**JE posted:**
```
Dr  Stock-in-Hand (BS Asset)              BHD 150
Cr  Closing Stock (Income Statement)      BHD 150
```

---

### Next Month — Incremental Reconciliation

Suppose 2 more units purchased (BHD 50) and 3 units sold in Month 2:
- New PI: Dr Purchases 50 / Cr AP 50
- tabBin closing = 5 units @ BHD 25 = **BHD 125**
- Stock-in-Hand GL (from last PAE) = **BHD 150** (opening stock for this period)
- Net change = 125 − 150 = **−BHD 25** (closing < opening → net stock consumed)

**JE posted:**
```
Dr  Closing Stock (Income Statement)      BHD 25
Cr  Stock-in-Hand (BS Asset)             BHD 25
```

Stock-in-Hand BS = 150 − 25 = **125** ✓ (matches tabBin)

---

## 4. GL / Ledger Reflection (Month 1)

| Account | Dr | Cr | Net |
|---|---|---|---|
| Purchases (Expense) | 250 (PI) | — | 250 Dr |
| Accounts Payable | — | 250 | 250 Cr |
| Accounts Receivable | 160 | — | 160 Dr |
| Sales Revenue | — | 160 | 160 Cr |
| Stock-in-Hand (BS Asset) | 150 (PAE) | — | 150 Dr |
| Closing Stock (IS Income) | — | 150 (PAE) | 150 Cr |

**P&L — Trading Account view:**
```
INCOME
  Sales Revenue                     160 Cr
  Closing Stock (Income Statement)  150 Cr   ← PAE credit (closing stock)

DIRECT EXPENSES
  Purchases                         250 Dr   ← Purchase Invoice

GROSS PROFIT                         60 Cr   ✓

COGS (implicit) = 0 + 250 − 150 = 100  ✓
```

**Balance Sheet:**
```
CURRENT ASSETS
  Stock-in-Hand                     150      ← PAE debit (opening stock for next period)
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
| Add: Gross Purchases | SLE `stock_value_difference` (positive) from PI/PR |
| Less: Purchase Returns | SLE `stock_value_difference` (negative) from PI/PR |
| Less: Closing Stock (Live) | tabBin (if `to_date` ≥ today) or cumulative SLE |
| COGS | Opening + Net Purchases − Closing |
| Gross Profit | Net Sales − COGS |

> The report reads stock values directly from the Stock Ledger (`tabBin` / SLE), not from GL accounts. This gives a **real-time view** of the trading position even before the month-end PAE is posted.

**Expected output with test data:**
```
SALES
  Gross Sales Revenue          160 Cr
NET SALES REVENUE              160 Cr

COST OF GOODS SOLD
  Opening Stock                  0 Dr
  Add: Gross Purchases         250 Dr
  Net Purchases                250 Dr
  Goods Available for Sale     250
  Less: Closing Stock          150 Cr
NET COGS                       100 Dr

GROSS PROFIT                    60 Cr
```

---

## 6. Standard P&L Report (ERPNext) After PAE

**Path:** Accounts → Reports → Profit and Loss Statement

```
Income
  Sales Revenue                  160
  Closing Stock (IS)             150   ← PAE credit (closing stock recognised)
  ──────────────────────────────────
  Total Income                   310

Direct Expenses
  Purchases                      250   ← Purchase Invoices
  ──────────────────────────────────
  Total Expenses                 250

Gross Profit                      60   ✓
```

**Before PAE is submitted**, the P&L shows Purchases = 250 as a cost with no Closing Stock credit, overstating COGS. The PAE is the period-end correction that credits Closing Stock IS (BHD 150) and brings GP from −90 to the correct +60.

---

## 7. Summary of Key Rules

| Rule | Detail |
|---|---|
| PAE only for periodic companies | Controller rejects if `enable_perpetual_inventory = 1` |
| Purchases must not post to Stock-in-Hand | Route PI expense accounts to a **Purchases (Expense)** account; posting to Stock-in-Hand corrupts the opening stock comparison |
| Closing Stock Account | Must be an **Income** root-type account (form filter enforces `root_type = Income`) |
| Stock-in-Hand Account | Must be a **Stock / Asset** root-type account updated only by PAE |
| Multiple stock accounts | Set `account` on each Warehouse master; ERPNext splits automatically |
| Amend support | PAE is submittable; amend cancels the linked JE and recreates |
