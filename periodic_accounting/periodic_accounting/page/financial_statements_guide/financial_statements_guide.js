frappe.pages["financial-statements-guide"].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Financial Statements — Accountant Reference",
		single_column: true,
	});

	$(wrapper).find(".page-content").html(get_guide_html());

	// Quick-navigate buttons
	page.add_inner_button(__("Trading Account"), function() {
		frappe.set_route("query-report", "Realtime Trading Account Report", {
			company: frappe.defaults.get_user_default("Company"),
			from_date: frappe.datetime.month_start(),
			to_date: frappe.datetime.get_today(),
		});
	}, __("Open Report"));

	page.add_inner_button(__("Gross & Net Profit"), function() {
		frappe.set_route("query-report", "Periodic Gross and Net Profit", {
			company: frappe.defaults.get_user_default("Company"),
			from_date: frappe.datetime.month_start(),
			to_date: frappe.datetime.get_today(),
		});
	}, __("Open Report"));

	page.add_inner_button(__("Balance Sheet"), function() {
		frappe.set_route("query-report", "Periodic Balance Sheet", {
			company: frappe.defaults.get_user_default("Company"),
			from_date: frappe.datetime.year_start(),
			to_date: frappe.datetime.get_today(),
		});
	}, __("Open Report"));
};

function get_guide_html() {
	return `
<div style="max-width:900px; margin:0 auto; padding:24px 16px; font-family:var(--font-stack); color:var(--text-color); line-height:1.7;">

<!-- ── HEADER ── -->
<div style="background:linear-gradient(135deg,#1565c0,#0d47a1); color:#fff; border-radius:12px; padding:32px 36px; margin-bottom:32px;">
  <h1 style="margin:0 0 8px; font-size:1.8em; font-weight:700;">Periodic Accounting — Financial Statements</h1>
  <p style="margin:0; opacity:0.88; font-size:1.05em;">How Tally-style reports work in ERPNext with non-perpetual inventory</p>
</div>

<!-- ── TALLY VS ERPNEXT OVERVIEW ── -->
<div style="${card()}">
  <h2 style="${h2()}">Tally vs ERPNext — Side by Side</h2>
  <p>In Tally, three reports form a linked financial statement set. This app replicates that structure for ERPNext (non-perpetual inventory):</p>
  <table style="${table()}">
    <thead><tr style="background:var(--subtle-fg);">
      <th style="${th()}">Tally Report</th>
      <th style="${th()}">ERPNext Equivalent</th>
      <th style="${th()}">Data Source</th>
    </tr></thead>
    <tbody>
      <tr>
        <td style="${td()}"><strong>Trading Account</strong></td>
        <td style="${td()}">Realtime Trading Account Report</td>
        <td style="${td()}">SLE (stock) + GL (sales)</td>
      </tr>
      <tr style="background:var(--subtle-fg);">
        <td style="${td()}"><strong>Profit &amp; Loss</strong></td>
        <td style="${td()}">Periodic Gross and Net Profit</td>
        <td style="${td()}">SLE (stock) + GL (income &amp; expenses)</td>
      </tr>
      <tr>
        <td style="${td()}"><strong>Balance Sheet</strong></td>
        <td style="${td()}">Periodic Balance Sheet</td>
        <td style="${td()}">GL (all accounts) + SLE override for stock</td>
      </tr>
    </tbody>
  </table>
</div>

<!-- ── WHY TWO DATA SOURCES ── -->
<div style="${card()}">
  <h2 style="${h2()}">Why Two Data Sources? (SLE + GL)</h2>
  <p>ERPNext uses <strong>non-perpetual inventory</strong> for this company. This means:</p>
  <ul>
    <li>The <strong>General Ledger (GL)</strong> is updated by Purchase Invoice, Sales Invoice, and other financial vouchers — it records money flows (revenue, expenses, payables, receivables).</li>
    <li>The <strong>Stock Ledger Entry (SLE)</strong> is updated by Purchase Receipt, Delivery Note, Stock Entry, etc. — it records physical stock movements and valuations.</li>
    <li>The GL does <em>not</em> automatically post entries when stock moves (that is perpetual inventory). The stock value in the GL may lag or differ from actual stock.</li>
  </ul>
  <div style="background:#e3f2fd; border-left:4px solid #1565c0; padding:12px 16px; border-radius:0 8px 8px 0; margin-top:12px;">
    <strong>Rule of thumb:</strong> For money amounts (sales revenue, indirect expenses, payables) — use GL.
    For stock values (opening, closing, COGS) — use SLE.
  </div>
</div>

<!-- ── COGS FORMULA ── -->
<div style="${card()}">
  <h2 style="${h2()}">COGS Formula (The Core Equation)</h2>
  <div style="background:#f8f9fa; border:1px solid var(--border-color); border-radius:8px; padding:20px; font-family:monospace; font-size:0.97em; margin-bottom:16px;">
    <div style="color:#1565c0; font-weight:700; font-size:1.1em;">Cost of Goods Sold  =</div>
    <div style="margin-top:8px; padding-left:24px;">
      Opening Stock &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← <em>SLE cumulative up to (from_date − 1)</em><br>
      + Local Purchases &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← <em>SLE from Purchase Receipt (company currency)</em><br>
      + Import Purchases &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← <em>SLE from Purchase Receipt (foreign currency)</em><br>
      + Landing Costs (LCV) &nbsp;← <em>SLE from Landed Cost Voucher</em><br>
      +/− Stock Adjustments &nbsp;← <em>SLE from Stock Entry / Stock Reconciliation</em><br>
      − Closing Stock &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;← <em>SLE cumulative up to to_date (or Bin if today)</em><br>
      <span style="border-top:2px solid #333; display:inline-block; margin-top:8px; padding-top:4px; font-weight:700;">= COGS</span>
    </div>
  </div>
  <p><strong>Tally equivalence:</strong> Tally uses the same formula. Opening Stock + Purchases − Closing Stock = Cost of Goods Sold. The difference here is that purchases are split by currency to distinguish local from import.</p>
</div>

<!-- ── LOCAL vs IMPORT ── -->
<div style="${card()}">
  <h2 style="${h2()}">Local vs Import Purchase Classification</h2>
  <p>Purchases are classified at the <strong>Stock Ledger Entry</strong> level by looking at the source voucher's currency:</p>
  <table style="${table()}">
    <thead><tr style="background:var(--subtle-fg);">
      <th style="${th()}">SLE Voucher Type</th>
      <th style="${th()}">Currency Check</th>
      <th style="${th()}">Classified As</th>
    </tr></thead>
    <tbody>
      <tr>
        <td style="${td()}">Purchase Receipt</td>
        <td style="${td()}">PR.currency = company currency</td>
        <td style="${td()}"><span style="color:#2e7d32; font-weight:600;">Local Purchase</span></td>
      </tr>
      <tr style="background:var(--subtle-fg);">
        <td style="${td()}">Purchase Receipt</td>
        <td style="${td()}">PR.currency ≠ company currency</td>
        <td style="${td()}"><span style="color:#e65100; font-weight:600;">Import Purchase</span></td>
      </tr>
      <tr>
        <td style="${td()}">Purchase Invoice (update_stock=Yes)</td>
        <td style="${td()}">PI.currency = company currency</td>
        <td style="${td()}"><span style="color:#2e7d32; font-weight:600;">Local Purchase</span></td>
      </tr>
      <tr style="background:var(--subtle-fg);">
        <td style="${td()}">Purchase Invoice (update_stock=Yes)</td>
        <td style="${td()}">PI.currency ≠ company currency</td>
        <td style="${td()}"><span style="color:#e65100; font-weight:600;">Import Purchase</span></td>
      </tr>
      <tr>
        <td style="${td()}">Landed Cost Voucher</td>
        <td style="${td()}">—</td>
        <td style="${td()}">Landing Costs (LCV)</td>
      </tr>
    </tbody>
  </table>
  <p style="margin-top:12px; color:var(--text-muted); font-size:0.9em;">
    The company's default currency is read from <strong>Company → Default Currency</strong>. For this company (Bahrain / BHD), any purchase in USD, SAR, EUR, etc. is treated as an Import purchase.
  </p>
</div>

<!-- ── TRADING ACCOUNT ── -->
<div style="${card()}">
  <h2 style="${h2()}">Report 1 — Trading Account (Dr | Cr)</h2>
  <p>Mirrors Tally's <em>Trading Account</em>. Shows two columns that must balance.</p>
  <table style="${table()}">
    <thead><tr style="background:var(--subtle-fg);">
      <th style="${th()}">Dr Side (Costs)</th>
      <th style="${th()}">Cr Side (Revenue)</th>
    </tr></thead>
    <tbody>
      <tr>
        <td style="${td()}">
          Opening Stock (SLE)<br>
          + Local Purchases (SLE — company currency)<br>
          + Import Purchases (SLE — foreign currency)<br>
          + Landing Costs, LCV (SLE)<br>
          +/− Stock Adjustments (SLE)<br>
          − Closing Stock moved to Cr<br>
          <strong>= Goods Available for Sale</strong><br>
          + Gross Profit (if profit → goes to Cr)
        </td>
        <td style="${td()}">
          Gross Sales Revenue (GL — Income A/c)<br>
          − Sales Returns (GL — Income A/c)<br>
          <strong>= Net Sales</strong><br>
          + Closing Stock (SLE)<br>
          + Gross Loss (if loss → goes to Dr)
        </td>
      </tr>
    </tbody>
  </table>
  <p><strong>Balance check row:</strong> Dr Total = Cr Total. If they balance, the Trading Account is arithmetically verified. A mismatch indicates a data entry error.</p>
  <p><strong>Gross Profit:</strong> Net Sales − COGS. A positive number means the company made money on buying and selling goods (before indirect expenses).</p>
</div>

<!-- ── G&NP ── -->
<div style="${card()}">
  <h2 style="${h2()}">Report 2 — Gross and Net Profit (P&amp;L)</h2>
  <p>Mirrors Tally's <em>Profit &amp; Loss Statement</em>. Single-column, flows from Income → COGS → Gross Profit → Indirect Expenses → Net Profit.</p>
  <div style="background:#f8f9fa; border:1px solid var(--border-color); border-radius:8px; padding:16px; font-family:monospace; font-size:0.9em;">
    <strong>Income ← GL</strong><br>
    &nbsp;&nbsp;Gross Sales Revenue<br>
    &nbsp;&nbsp;− Sales Returns<br>
    &nbsp;&nbsp;+ Other Income<br>
    <strong>= Total Income</strong><br><br>
    <strong>Cost of Goods Sold ← SLE</strong><br>
    &nbsp;&nbsp;Opening Stock<br>
    &nbsp;&nbsp;+ Local Purchases<br>
    &nbsp;&nbsp;+ Import Purchases<br>
    &nbsp;&nbsp;+ Landing Costs (LCV)<br>
    &nbsp;&nbsp;− Purchase Returns<br>
    &nbsp;&nbsp;+/− Stock Adjustments<br>
    &nbsp;&nbsp;− Closing Stock<br>
    <strong>= Net COGS</strong><br><br>
    <strong>Gross Profit = Total Income − COGS</strong><br><br>
    <strong>Indirect Expenses ← GL</strong><br>
    &nbsp;&nbsp;Salaries, Rent, Admin, etc.<br>
    &nbsp;&nbsp;(Purchase expense accounts excluded — already in COGS)<br><br>
    <strong>Net Profit = Gross Profit − Indirect Expenses</strong>
  </div>
  <div style="background:#fff3e0; border-left:4px solid #e65100; padding:12px 16px; border-radius:0 8px 8px 0; margin-top:16px;">
    <strong>Important:</strong> Purchase expense GL accounts (Local Purchases, Import Purchases) are <em>excluded</em> from Indirect Expenses. Without this exclusion, the purchase cost would be counted twice — once via SLE COGS and once via GL expense.
  </div>
</div>

<!-- ── BALANCE SHEET ── -->
<div style="${card()}">
  <h2 style="${h2()}">Report 3 — Balance Sheet</h2>
  <p>Standard ERPNext Balance Sheet structure with one important override: <strong>Stock accounts are replaced by the SLE cumulative value</strong> instead of the GL balance.</p>
  <table style="${table()}">
    <thead><tr style="background:var(--subtle-fg);">
      <th style="${th()}">Assets</th>
      <th style="${th()}">Liabilities + Equity</th>
    </tr></thead>
    <tbody>
      <tr>
        <td style="${td()}">
          Fixed Assets (GL)<br>
          Current Assets:<br>
          &nbsp;&nbsp;Cash &amp; Bank (GL)<br>
          &nbsp;&nbsp;Accounts Receivable (GL)<br>
          &nbsp;&nbsp;<strong>Closing Stock ← SLE</strong> (overrides GL stock A/c)<br>
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Opening Stock note (link)<br>
          &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Closing Stock note (link)
        </td>
        <td style="${td()}">
          Accounts Payable (GL)<br>
          Other Liabilities (GL)<br>
          Capital / Equity (GL)<br>
          <strong>Net Profit ← SLE-based P&amp;L</strong><br>
          &nbsp;&nbsp;(click to open Gross &amp; Net Profit report)
        </td>
      </tr>
    </tbody>
  </table>
  <p><strong>Stock-GL Gap warning:</strong> In non-perpetual inventory the GL stock account is never auto-updated. The balance sheet will show a gap equal to the closing stock value. To reconcile, post a journal entry:</p>
  <div style="background:#f8f9fa; border:1px solid var(--border-color); border-radius:8px; padding:12px 16px; font-family:monospace;">
    Dr &nbsp;Stock Account &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{closing_stock_value}<br>
    &nbsp;&nbsp;Cr &nbsp;P&amp;L / Equity &nbsp;&nbsp;{closing_stock_value}
  </div>
</div>

<!-- ── OPENING/CLOSING STOCK ── -->
<div style="${card()}">
  <h2 style="${h2()}">Opening Stock — The Tally Continuity Rule</h2>
  <p>In Tally, <strong>yesterday's closing stock is today's opening stock</strong>. This app implements the same rule:</p>
  <div style="background:#f8f9fa; border:1px solid var(--border-color); border-radius:8px; padding:16px; font-family:monospace; font-size:0.9em;">
    Opening Stock for period (A → B) =<br>
    &nbsp;&nbsp;get_closing_stock(to_date = A − 1 day)<br><br>
    Closing Stock for period (A → B) =<br>
    &nbsp;&nbsp;If B ≥ today: use tabBin (live stock value)<br>
    &nbsp;&nbsp;If B &lt; today: use SUM(SLE.stock_value_difference) up to B
  </div>
  <p>This means period reports are perfectly chainable: Period 1 closing = Period 2 opening, Period 2 closing = Period 3 opening — just like Tally.</p>
</div>

<!-- ── DRILL-DOWN MAP ── -->
<div style="${card()}">
  <h2 style="${h2()}">Drill-Down Links — What Opens Where</h2>
  <table style="${table()}">
    <thead><tr style="background:var(--subtle-fg);">
      <th style="${th()}">Row</th>
      <th style="${th()}">Drill-Down Report</th>
      <th style="${th()}">What It Shows</th>
    </tr></thead>
    <tbody>
      <tr><td style="${td()}">Gross Sales Revenue</td><td style="${td()}">Sales Register</td><td style="${td()}">GL income entries — the selling price</td></tr>
      <tr style="background:var(--subtle-fg);"><td style="${td()}">Local / Import Purchases</td><td style="${td()}">Purchase Stock Entries</td><td style="${td()}">SLE inward movements — the cost paid</td></tr>
      <tr><td style="${td()}">Opening Stock</td><td style="${td()}">Stock Balance (snapshot)</td><td style="${td()}">Stock value as of from_date − 1</td></tr>
      <tr style="background:var(--subtle-fg);"><td style="${td()}">Closing Stock</td><td style="${td()}">Stock Balance (period)</td><td style="${td()}">Stock value and movements for the period</td></tr>
      <tr><td style="${td()}">Net Cost of Goods Sold</td><td style="${td()}">Sales Stock Entries</td><td style="${td()}">SLE outward movements = cost of items sold (cross-check of COGS)</td></tr>
      <tr style="background:var(--subtle-fg);"><td style="${td()}">Stock Adjustments</td><td style="${td()}">Stock Ledger</td><td style="${td()}">Stock Entry / Reconciliation entries in the period</td></tr>
      <tr><td style="${td()}">Indirect Expense accounts</td><td style="${td()}">General Ledger</td><td style="${td()}">Individual GL postings for that account</td></tr>
      <tr style="background:var(--subtle-fg);"><td style="${td()}">Net Profit (Balance Sheet)</td><td style="${td()}">Gross &amp; Net Profit</td><td style="${td()}">Full P&amp;L breakdown including COGS formula</td></tr>
    </tbody>
  </table>
</div>

<!-- ── GLOSSARY ── -->
<div style="${card()}">
  <h2 style="${h2()}">Glossary</h2>
  <dl style="display:grid; grid-template-columns:170px 1fr; gap:8px 16px;">
    <dt style="font-weight:600;">SLE</dt><dd>Stock Ledger Entry — ERPNext's record of every physical stock movement. Contains item, warehouse, qty, rate, and <code>stock_value_difference</code>.</dd>
    <dt style="font-weight:600;">GLE / GL Entry</dt><dd>General Ledger Entry — the double-entry accounting record. Every financial voucher posts debits and credits here.</dd>
    <dt style="font-weight:600;">Bin</dt><dd>ERPNext's live stock snapshot per item+warehouse. Used for closing stock when to_date ≥ today; SLE cumulative used for historical dates.</dd>
    <dt style="font-weight:600;">LCV</dt><dd>Landed Cost Voucher — adds freight, customs, and other charges to the cost of an existing Purchase Receipt. Creates SLE adjustments.</dd>
    <dt style="font-weight:600;">Non-perpetual inventory</dt><dd>Stock accounts in the GL are not automatically updated when stock moves. The stock value is tracked only in SLE; the GL reflects purchase expense accounts instead.</dd>
    <dt style="font-weight:600;">stock_value_difference</dt><dd>The key SLE field. Positive = stock value added (purchase, receipt). Negative = stock value removed (sale, issue). Summing all SLE gives the cumulative stock value.</dd>
    <dt style="font-weight:600;">Opening Stock</dt><dd>SLE cumulative value as of (from_date − 1). Equivalent to Tally's "Opening Balance" for stock.</dd>
    <dt style="font-weight:600;">Closing Stock</dt><dd>SLE cumulative value as of to_date (or Bin if live). Shown in both the COGS section (as a deduction) and Balance Sheet (as a current asset).</dd>
  </dl>
</div>

</div>`;
}

// ── Style helpers ──────────────────────────────────────────────────────────────
function card() {
	return "background:var(--card-bg); border:1px solid var(--border-color); border-radius:10px; padding:24px 28px; margin-bottom:24px; box-shadow:0 1px 4px rgba(0,0,0,0.06);";
}
function h2() {
	return "margin:0 0 14px; font-size:1.2em; color:var(--heading-color); border-bottom:2px solid var(--primary); padding-bottom:8px; display:inline-block;";
}
function table() {
	return "width:100%; border-collapse:collapse; font-size:0.93em;";
}
function th() {
	return "text-align:left; padding:8px 12px; font-weight:600; border-bottom:2px solid var(--border-color);";
}
function td() {
	return "padding:8px 12px; border-bottom:1px solid var(--border-color); vertical-align:top;";
}
