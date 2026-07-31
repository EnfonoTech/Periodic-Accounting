frappe.pages["audit-guide"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Auditor's Field Guide — Periodic Accounting"),
		single_column: true,
	});

	page.add_action_item(__("Audit Trading Account"), () => {
		frappe.set_route("query-report", "Audit Trading Account Report");
	});
	page.add_action_item(__("Item COGS Analysis"), () => {
		frappe.set_route("query-report", "Item COGS Analysis Report");
	});

	$(`<style>
		.ag-wrap {
			max-width: 820px;
			padding: 28px 36px 72px;
			font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
			font-size: 14px;
			color: #1a2b3c;
			line-height: 1.65;
		}
		.ag-section { margin-bottom: 48px; }

		/* ── Header ─────────────────────────────────────────────────────── */
		.ag-page-header {
			margin-bottom: 36px;
			padding-bottom: 24px;
			border-bottom: 2px solid #d0dce8;
		}
		.ag-eyebrow {
			font-size: 10.5px;
			letter-spacing: .11em;
			text-transform: uppercase;
			color: #1B4F8A;
			font-weight: 600;
			margin-bottom: 6px;
		}
		.ag-h1 {
			font-family: Georgia, "Times New Roman", serif;
			font-size: 26px;
			font-weight: normal;
			color: #0d1b2a;
			line-height: 1.25;
			margin: 0 0 10px;
		}
		.ag-lead { color: #3b5068; max-width: 580px; margin: 0; }

		/* ── Section headings ────────────────────────────────────────────── */
		.ag-h2 {
			font-family: Georgia, "Times New Roman", serif;
			font-size: 19px;
			font-weight: normal;
			color: #0d1b2a;
			margin: 0 0 4px;
		}
		.ag-h2-sub {
			font-size: 13px;
			color: #627d98;
			margin: 0 0 20px;
			padding-bottom: 14px;
			border-bottom: 1px solid #d0dce8;
		}
		.ag-h3 {
			font-size: 11px;
			font-weight: 700;
			letter-spacing: .09em;
			text-transform: uppercase;
			color: #3b5068;
			margin: 28px 0 12px;
		}

		/* ── Audit value cards ───────────────────────────────────────────── */
		.ag-audit-pair {
			display: grid;
			grid-template-columns: 1fr 1fr;
			gap: 14px;
		}
		.ag-audit-card {
			border: 1px solid #cdd8e4;
			border-top: 3px solid #1b4f8a;
			border-radius: 7px;
			background: #fff;
			padding: 18px 20px;
		}
		.ag-audit-card.green { border-top-color: #2e7d32; }
		.ag-audit-card-title {
			font-weight: 700;
			font-size: 13px;
			color: #0d1b2a;
			margin-bottom: 14px;
		}
		.ag-audit-point {
			display: flex;
			gap: 10px;
			font-size: 13px;
			color: #3b5068;
			margin-bottom: 10px;
			line-height: 1.5;
		}
		.ag-audit-point:last-child { margin-bottom: 0; }
		.ag-audit-dot {
			width: 6px; height: 6px;
			border-radius: 50%;
			background: #1b4f8a;
			flex-shrink: 0;
			margin-top: 7px;
		}
		.ag-audit-card.green .ag-audit-dot { background: #2e7d32; }
		.ag-audit-point strong { color: #0d1b2a; }

		/* ── Workflow ─────────────────────────────────────────────────────── */
		.ag-workflow {
			display: flex;
			align-items: center;
			gap: 0;
			background: #fff;
			border: 1px solid #cdd8e4;
			border-radius: 8px;
			padding: 20px 18px;
			overflow-x: auto;
		}
		.ag-wf-step {
			flex-shrink: 0;
			text-align: center;
			width: 108px;
		}
		.ag-wf-icon {
			width: 38px; height: 38px;
			border-radius: 50%;
			background: #ebf2fb;
			display: flex; align-items: center; justify-content: center;
			margin: 0 auto 8px;
			font-size: 16px;
		}
		.ag-wf-icon.green { background: #e4f4ed; }
		.ag-wf-icon.red   { background: #faedeb; }
		.ag-wf-label {
			font-size: 11px;
			color: #3b5068;
			line-height: 1.35;
		}
		.ag-wf-label strong { display: block; color: #0d1b2a; font-size: 11.5px; margin-bottom: 2px; }
		.ag-wf-arrow {
			color: #cdd8e4;
			font-size: 20px;
			padding: 0 2px;
			margin-bottom: 22px;
			flex-shrink: 0;
		}

		/* ── Check cards ──────────────────────────────────────────────────── */
		.ag-checks { display: flex; flex-direction: column; gap: 10px; }
		.ag-card {
			background: #fff;
			border: 1px solid #cdd8e4;
			border-left: 4px solid #cdd8e4;
			border-radius: 6px;
			padding: 14px 16px;
			display: grid;
			grid-template-columns: 28px 1fr;
			gap: 0 12px;
		}
		.ag-card.pass  { border-left-color: #1e6b42; background: #e4f4ed; border-color: #a8d8be; }
		.ag-card.fail  { border-left-color: #b0311e; background: #faedeb; border-color: #e8b5ae; }
		.ag-card.warn  { border-left-color: #9a5f00; background: #fef4e0; border-color: #f0c878; }
		.ag-card.info  { border-left-color: #1b4f8a; background: #ebf2fb; border-color: #b8d0ec; }
		.ag-card-icon { grid-row: 1/3; font-size: 20px; align-self: start; padding-top: 1px; line-height: 1; }
		.ag-card-title { font-weight: 700; font-size: 13px; color: #0d1b2a; margin-bottom: 4px; }
		.ag-card-title .ag-chip {
			display: inline-block;
			font-family: "Courier New", monospace;
			font-size: 10.5px;
			background: rgba(0,0,0,.08);
			padding: 1px 5px;
			border-radius: 3px;
			margin-left: 5px;
			font-weight: normal;
		}
		.ag-card-body { font-size: 13px; color: #3b5068; line-height: 1.55; }
		.ag-card-body strong { color: #0d1b2a; }

		/* ── Two-column grid ──────────────────────────────────────────────── */
		.ag-two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

		/* ── Formula block ────────────────────────────────────────────────── */
		.ag-formula {
			background: #0d1b2a;
			color: #c8d8e8;
			border-radius: 6px;
			padding: 14px 18px;
			font-family: "Courier New", monospace;
			font-size: 12.5px;
			line-height: 1.9;
			overflow-x: auto;
			margin: 14px 0;
		}
		.ag-formula .hl  { color: #7ec8e3; }
		.ag-formula .eq  { color: #f0c878; font-weight: bold; }
		.ag-formula .note { color: #4d6a84; font-size: 11px; }

		/* ── Column guide table ───────────────────────────────────────────── */
		.ag-table-wrap { overflow-x: auto; border: 1px solid #cdd8e4; border-radius: 6px; background: #fff; }
		.ag-table { width: 100%; border-collapse: collapse; }
		.ag-table th {
			font-size: 10px;
			letter-spacing: .09em;
			text-transform: uppercase;
			color: #627d98;
			text-align: left;
			border-bottom: 2px solid #cdd8e4;
			padding: 7px 12px;
			background: #eef2f7;
		}
		.ag-table td {
			padding: 9px 12px;
			font-size: 13px;
			color: #3b5068;
			border-bottom: 1px solid #e8eef4;
			vertical-align: top;
			line-height: 1.5;
		}
		.ag-table tr:last-child td { border-bottom: none; }
		.ag-table td:first-child {
			font-family: "Courier New", monospace;
			font-size: 11.5px;
			color: #1b4f8a;
			white-space: nowrap;
			background: #ebf2fb;
			font-weight: 600;
		}
		.ag-table td strong { color: #0d1b2a; }
		.ag-pill {
			display: inline-block;
			font-size: 10.5px;
			font-weight: 700;
			padding: 1px 6px;
			border-radius: 10px;
			vertical-align: middle;
		}
		.ag-pill-pass { background: #e4f4ed; color: #1e6b42; }
		.ag-pill-fail { background: #faedeb; color: #b0311e; }
		.ag-pill-warn { background: #fef4e0; color: #9a5f00; }

		/* ── Issues table ─────────────────────────────────────────────────── */
		.ag-issues td:first-child { color: #b0311e; background: #faedeb; font-size: 12px; }
		.ag-issues td:nth-child(2) { color: #0d1b2a; background: #fff; }
		.ag-issues td:nth-child(3) { color: #1e6b42; background: #e4f4ed; font-weight: 600; font-size: 12px; }

		/* ── Cross-ref strip ──────────────────────────────────────────────── */
		.ag-xref {
			background: #0d1b2a;
			color: #c8d8e8;
			border-radius: 8px;
			padding: 20px 24px;
		}
		.ag-xref h3 {
			font-family: Georgia, serif;
			font-size: 15px;
			font-weight: normal;
			color: #fff;
			margin: 0 0 12px;
			text-transform: none;
			letter-spacing: 0;
		}
		.ag-xref ol { padding-left: 18px; display: flex; flex-direction: column; gap: 8px; }
		.ag-xref li { font-size: 13px; line-height: 1.55; }
		.ag-xref .hl { color: #7ec8e3; font-weight: 600; }

		/* ── Checklist ────────────────────────────────────────────────────── */
		.ag-checklist { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 5px; }
		.ag-checklist li {
			display: flex; align-items: flex-start; gap: 10px;
			background: #fff;
			border: 1px solid #cdd8e4;
			border-radius: 5px;
			padding: 9px 14px;
			font-size: 13px;
			color: #3b5068;
		}
		.ag-checklist li .ag-box {
			width: 15px; height: 15px;
			border: 2px solid #cdd8e4;
			border-radius: 3px;
			flex-shrink: 0;
			margin-top: 2px;
		}
		.ag-checklist li strong { color: #0d1b2a; }
		.ag-cl-group {
			font-size: 10px;
			letter-spacing: .1em;
			text-transform: uppercase;
			color: #627d98;
			font-weight: 600;
			padding: 10px 0 2px;
			background: transparent;
			border: none;
		}
		.ag-cl-group .ag-box { display: none; }

		/* ── Report links ─────────────────────────────────────────────────── */
		.ag-report-links {
			display: flex; gap: 10px; margin-bottom: 24px; flex-wrap: wrap;
		}
		.ag-report-btn {
			display: inline-flex; align-items: center; gap: 6px;
			padding: 8px 16px;
			border-radius: 5px;
			font-size: 13px;
			font-weight: 600;
			cursor: pointer;
			border: none;
			text-decoration: none;
			transition: opacity .15s;
		}
		.ag-report-btn:hover { opacity: .85; }
		.ag-report-btn.primary { background: #1b4f8a; color: #fff; }
		.ag-report-btn.secondary { background: #ebf2fb; color: #1b4f8a; border: 1px solid #b8d0ec; }
	</style>`).appendTo("head");

	$(page.main).html(`
		<div class="ag-wrap">

			<!-- Header -->
			<div class="ag-page-header">
				<div class="ag-eyebrow">ERPNext · Periodic Inventory</div>
				<h1 class="ag-h1">Auditor's Field Guide</h1>
				<p class="ag-lead">How to verify inventory accuracy and COGS correctness at period-end using the Audit Trading Account and Item COGS Analysis reports.</p>
			</div>

			<!-- Quick launch -->
			<div class="ag-report-links">
				<button class="ag-report-btn primary" onclick="frappe.set_route('query-report','Audit Trading Account Report')">
					📊 Open Audit Trading Account
				</button>
				<button class="ag-report-btn secondary" onclick="frappe.set_route('query-report','Item COGS Analysis Report')">
					📋 Open Item COGS Analysis
				</button>
			</div>

			<!-- Audit value of both reports -->
			<div class="ag-section">
				<h2 class="ag-h2">How These Reports Support Auditing</h2>
				<p class="ag-h2-sub">Both reports read directly from Stock Ledger Entries — the system-generated source of truth for every stock movement. They cannot be distorted by manual journals or posting errors the way a plain P&amp;L can.</p>

				<div class="ag-audit-pair">

					<div class="ag-audit-card">
						<div class="ag-audit-card-title">📊 Audit Trading Account</div>

						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Reconstructs COGS independently of GL.</strong> The formula COGS is built from Stock Ledger Entries, not from GL account balances — so it cannot be inflated or suppressed through manual journals.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Two automated pass/fail checks.</strong> COGS Variance and Bin vs Stock GL are calculated and flagged automatically — no manual reconciliation spreadsheet needed.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Purchase split by type.</strong> Local PR and Import PR trace to Purchase Receipts; LCV traces to Landed Cost Vouchers; PI Rate Adjustment traces to Purchase Invoices posted at a different rate than the receipt. Each line has its own source document for verification.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Reconciliation to Trial Balance</strong> proves the formula figure against the Cost of Goods Sold account's own net movement, so the report cannot disagree with the Trial Balance unnoticed.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Breakdown by Warehouse or Item Group</strong> lets auditors scope the entire analysis to a specific stock location or product category.</span>
						</div>
					</div>

					<div class="ag-audit-card green">
						<div class="ag-audit-card-title">📋 Item COGS Analysis</div>

						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Every item is individually accountable.</strong> One row per item means no movement can be hidden in a company-wide total — every item must individually pass both checks.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Variance column mathematically verifies the stock equation.</strong> Opening + Inflows − Outflows − Closing must equal zero for every item. A non-zero result proves a posting error exists for that specific item.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>COGS Diff confirms SLE and GL are in agreement per item.</strong> If Sales COGS from SLE does not match GL COGS exactly, the difference is highlighted — the auditor knows which item caused the company-level COGS Variance.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Drill-down path is built in.</strong> Sorting COGS Diff or Variance descending immediately surfaces the highest-risk items, cutting investigation time from hours to minutes.</span>
						</div>
						<div class="ag-audit-point">
							<div class="ag-audit-dot"></div>
							<span><strong>Transfer balance is verifiable.</strong> Transfer In and Transfer Out are shown separately — running the report company-wide confirms no stock has been lost or duplicated between warehouses.</span>
						</div>
					</div>

				</div>
			</div>

			<!-- Workflow -->
			<div class="ag-section">
				<h2 class="ag-h2">Audit Workflow</h2>
				<p class="ag-h2-sub">Run these steps in order at each period-end. Trading Account shows the total picture; Item COGS shows which items caused any discrepancy.</p>

				<div class="ag-workflow">
					<div class="ag-wf-step">
						<div class="ag-wf-icon">📅</div>
						<div class="ag-wf-label"><strong>Set period</strong>Select company, from / to date</div>
					</div>
					<div class="ag-wf-arrow">›</div>
					<div class="ag-wf-step">
						<div class="ag-wf-icon">📊</div>
						<div class="ag-wf-label"><strong>Run Trading Account</strong>Check all indicators</div>
					</div>
					<div class="ag-wf-arrow">›</div>
					<div class="ag-wf-step">
						<div class="ag-wf-icon red">❌</div>
						<div class="ag-wf-label"><strong>Any red?</strong>Drill into Item COGS</div>
					</div>
					<div class="ag-wf-arrow">›</div>
					<div class="ag-wf-step">
						<div class="ag-wf-icon">🔍</div>
						<div class="ag-wf-label"><strong>Identify item</strong>Sort Variance &amp; COGS Diff</div>
					</div>
					<div class="ag-wf-arrow">›</div>
					<div class="ag-wf-step">
						<div class="ag-wf-icon">🔗</div>
						<div class="ag-wf-label"><strong>Trace voucher</strong>Stock Ledger → fix</div>
					</div>
					<div class="ag-wf-arrow">›</div>
					<div class="ag-wf-step">
						<div class="ag-wf-icon green">✅</div>
						<div class="ag-wf-label"><strong>All green</strong>Sign off period</div>
					</div>
				</div>
			</div>

			<!-- Trading Account -->
			<div class="ag-section">
				<h2 class="ag-h2">Audit Trading Account Report</h2>
				<p class="ag-h2-sub">Opens with a summary strip (Net Sales · COGS) and a bar chart. The table applies the traditional periodic formula reconstructed from Stock Ledger Entries.</p>

				<div class="ag-formula">
<span class="hl">Opening Stock</span>  +  <span class="hl">Net Purchases</span>  (Local PR + Import PR + LCV + PI Rate Adj − Returns)
−  <span class="hl">Closing Stock</span>
<span class="eq">  =  Formula COGS</span>
<span class="note">This must equal perpetual GL COGS (Dr on Cost of Goods Sold accounts). If not → COGS Variance ≠ 0.</span>
				</div>

				<div class="ag-h3">The 4 checks every auditor must verify</div>
				<div class="ag-checks">

					<div class="ag-card fail">
						<div class="ag-card-icon">❌</div>
						<div class="ag-card-title">COGS Variance <span class="ag-chip">must be 0.00</span></div>
						<div class="ag-card-body">
							Formula COGS (SLE) differs from perpetual GL COGS.<br>
							<strong>Likely causes:</strong> Company still in Periodic mode; a delivery was backdated after a valuation rate change; a Stock Reconciliation posted without a linked GL entry.<br>
							<strong>Action:</strong> Enable Perpetual Inventory, then re-run. If still non-zero, open Item COGS Analysis → sort COGS Diff column descending → the top item caused it.
						</div>
					</div>

					<div class="ag-card fail">
						<div class="ag-card-icon">❌</div>
						<div class="ag-card-title">Bin vs Stock Account GL <span class="ag-chip">must be 0.00</span></div>
						<div class="ag-card-body">
							Live Bin stock value differs from the GL Stock Account balance.<br>
							<strong>Likely causes:</strong> A voucher cancelled without reversing its GL entry; a direct journal posted to the stock account; perpetual inventory enabled mid-year with an opening balance mismatch.<br>
							<strong>Action:</strong> GL Entry report → filter to Stock Account → find a Dr/Cr with no matching SLE reference.
						</div>
					</div>

					<div class="ag-card warn">
						<div class="ag-card-icon">⚠</div>
						<div class="ag-card-title">Cost of goods sold — reasonableness check</div>
						<div class="ag-card-body">
							Compare NET COGS against net sales for the period, and against the prior period.<br>
							<strong>Watch for:</strong> Sudden margin compression → purchase return incorrectly credited to COGS; sudden expansion → sales return not linked to original invoice; imported goods LCV posted in the wrong period inflating this period's purchases.
						</div>
					</div>

					<div class="ag-card info">
						<div class="ag-card-icon">ℹ</div>
						<div class="ag-card-title">Period continuity — Opening must equal prior Closing</div>
						<div class="ag-card-body">
							Run the report for two consecutive periods. <strong>Closing Stock</strong> of period 1 must exactly equal <strong>Opening Stock</strong> of period 2.<br>
							If they differ: a backdated entry was posted in the gap, or an item's valuation method (FIFO / Moving Average) was changed without an adjustment.
						</div>
					</div>

				</div>

				<div class="ag-h3">Reading purchase split lines</div>
				<div class="ag-two">
					<div class="ag-card info">
						<div class="ag-card-icon">🏠</div>
						<div class="ag-card-title">Local Purchases</div>
						<div class="ag-card-body">Purchase Receipts in <strong>company default currency</strong>. Cross-check total against the Purchase Receipt report filtered by company currency.</div>
					</div>
					<div class="ag-card info">
						<div class="ag-card-icon">✈</div>
						<div class="ag-card-title">Import Purchases</div>
						<div class="ag-card-body">Purchase Receipts in <strong>foreign currency</strong>. Should always be accompanied by Landed Cost Vouchers for freight and customs.</div>
					</div>
					<div class="ag-card info">
						<div class="ag-card-icon">🚢</div>
						<div class="ag-card-title">Landed Cost Vouchers</div>
						<div class="ag-card-body">Raises valuation of imported goods. Verify LCV is posted in the <strong>same period</strong> as the related Purchase Receipt — timing mismatches distort COGS.</div>
					</div>
					<div class="ag-card warn">
						<div class="ag-card-icon">Δ</div>
						<div class="ag-card-title">PI Rate Adjustment</div>
						<div class="ag-card-body">Posted when Purchase Invoice rate ≠ Purchase Receipt rate. A <strong>negative</strong> value means the invoice was below the receipt valuation — verify this is intentional.</div>
					</div>
				</div>
			</div>

			<!-- Item COGS -->
			<div class="ag-section">
				<h2 class="ag-h2">Item COGS Analysis Report</h2>
				<p class="ag-h2-sub">One row per item. Two audit checks per row — <strong>Variance</strong> (stock equation) and <strong>COGS Diff</strong> (SLE vs GL). Both must be zero for every item before period-end sign-off.</p>

				<div class="ag-h3">Column guide</div>
				<div class="ag-table-wrap">
					<table class="ag-table">
						<thead>
							<tr>
								<th>Column</th>
								<th>What it is</th>
								<th>Audit action if non-zero</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td>Opening</td>
								<td>Cumulative SLE value before the period start date. Should equal Closing of the prior period.</td>
								<td>Run report for prior period — confirm Closing matches.</td>
							</tr>
							<tr>
								<td>Local PR / Import PR</td>
								<td>Purchase Receipts in company vs foreign currency. Positive inflows to stock value.</td>
								<td>Cross-check against the Purchase Receipt report for the period. Import PR should each have a corresponding LCV.</td>
							</tr>
							<tr>
								<td>LCV</td>
								<td>Landed Cost Voucher uplift to valuation.</td>
								<td>Confirm posting date matches the related PR period. Late LCVs distort current-period COGS.</td>
							</tr>
							<tr>
								<td>PI Rate Adj</td>
								<td>Valuation adjustment when PI rate ≠ PR rate. Can be positive or negative.</td>
								<td>Large negative values signal a systematic pricing discrepancy — verify with supplier invoices.</td>
							</tr>
							<tr>
								<td>Pur Returns</td>
								<td>ABS value of stock reduction from PR / PI returns.</td>
								<td>Confirm return is linked to the original Purchase Receipt — unlinked returns misstate opening stock.</td>
							</tr>
							<tr>
								<td>Transfer In / Out</td>
								<td>Material Transfer Stock Entries — value moves between warehouses, not a cost event.</td>
								<td>Transfer In must equal Transfer Out across all warehouses for the same items.</td>
							</tr>
							<tr>
								<td>Mfg / Issue Out</td>
								<td>Stock consumed by Work Orders or Material Issues.</td>
								<td>Reconcile with Production report. Unexpected values indicate phantom issues.</td>
							</tr>
							<tr>
								<td>Sales COGS</td>
								<td>Stock value reduction from Sales Invoices and Delivery Notes.</td>
								<td>Must equal GL COGS in perpetual mode — see COGS Diff column.</td>
							</tr>
							<tr>
								<td>Sales Ret In</td>
								<td>Stock value increase from sales returns.</td>
								<td>Confirm each return is linked to an original Sales Invoice — unlinked returns inflate closing stock.</td>
							</tr>
							<tr>
								<td>Closing</td>
								<td>Live Bin value (current period) or cumulative SLE (historical).</td>
								<td>Should equal Stock Balance report for the same item and date.</td>
							</tr>
							<tr>
								<td><strong>Variance ✓</strong></td>
								<td><strong>Opening + Inflows − Outflows − Closing. Must be 0.000.</strong><br>
									<span class="ag-pill ag-pill-pass">✓ Green = clean</span>&nbsp;
									<span class="ag-pill ag-pill-fail">⚠ Red = investigate</span>
								</td>
								<td>Non-zero = cancelled or partially-posted SLE. Open Stock Ledger, filter to this item, find the unbalanced entry.</td>
							</tr>
							<tr>
								<td><strong>GL COGS</strong></td>
								<td>COGS posted to GL by the perpetual engine (Dr Cost of Goods Sold).</td>
								<td>Should match Sales COGS exactly. Difference lands in COGS Diff column.</td>
							</tr>
							<tr>
								<td><strong>COGS Diff</strong></td>
								<td><strong>Sales COGS − GL COGS. Must be 0.000.</strong><br>
									<span class="ag-pill ag-pill-pass">✓ Green = clean</span>&nbsp;
									<span class="ag-pill ag-pill-warn">△ Amber = investigate</span>
								</td>
								<td>Delivery posted at a different rate than GL. Check if LCV was applied after delivery, or if a manual GL entry exists.</td>
							</tr>
						</tbody>
					</table>
				</div>

				<div class="ag-h3">Using filters efficiently</div>
				<div class="ag-two">
					<div class="ag-card info">
						<div class="ag-card-icon">🏢</div>
						<div class="ag-card-title">Filter by Warehouse</div>
						<div class="ag-card-body">Audit a single stock location. Transfer In must equal Transfer Out across warehouses for the same item.</div>
					</div>
					<div class="ag-card info">
						<div class="ag-card-icon">📦</div>
						<div class="ag-card-title">Filter by Item Group</div>
						<div class="ag-card-body">Scope to a product category — e.g. Finished Goods separately from Raw Materials. Margin comparison is more meaningful within a category.</div>
					</div>
					<div class="ag-card info">
						<div class="ag-card-icon">☑</div>
						<div class="ag-card-title">Hide Fully-Zero Rows</div>
						<div class="ag-card-body">Removes items with no activity in the period. Enable this when your catalogue is large — focus only on items that moved.</div>
					</div>
					<div class="ag-card info">
						<div class="ag-card-icon">💼</div>
						<div class="ag-card-title">Filter by Cost Center</div>
						<div class="ag-card-body">Scopes GL COGS to a department. The Variance column is unaffected — it is SLE-based, not GL-based.</div>
					</div>
				</div>
			</div>

			<!-- Cross-ref -->
			<div class="ag-section">
				<div class="ag-xref">
					<h3>Cross-referencing both reports — when Trading Account shows red</h3>
					<ol>
						<li>Note the <span class="hl">COGS Variance</span> figure in the Trading Account (e.g. 750.00 Dr).</li>
						<li>Open <span class="hl">Item COGS Analysis</span> for the same company, period, and warehouse.</li>
						<li>Click the <span class="hl">COGS Diff</span> column header to sort descending — items with the largest SLE-vs-GL gap float to the top.</li>
						<li>The top items should account for the total variance. Open each item's <span class="hl">Stock Ledger</span> to find the specific voucher.</li>
						<li>Also sort the <span class="hl">Variance ✓</span> column — items with unbalanced SLE equations cause the Bin vs GL discrepancy in the Trading Account.</li>
					</ol>
				</div>
			</div>

			<!-- Common issues -->
			<div class="ag-section">
				<h2 class="ag-h2">Common Issues &amp; Fixes</h2>
				<p class="ag-h2-sub">Quick lookup when a check fails.</p>

				<div class="ag-table-wrap">
					<table class="ag-table ag-issues">
						<thead>
							<tr>
								<th>Symptom</th>
								<th>Most Likely Cause</th>
								<th>Fix</th>
							</tr>
						</thead>
						<tbody>
							<tr>
								<td>COGS Variance ❌</td>
								<td>Perpetual Inventory not enabled — no automatic COGS GL entries are posted when goods are delivered.</td>
								<td>Company → Enable Perpetual Inventory → re-run</td>
							</tr>
							<tr>
								<td>COGS Variance ❌ (perpetual on)</td>
								<td>A Landed Cost Voucher was posted after the delivery. GL COGS posted at original rate; SLE updated retroactively by LCV.</td>
								<td>Repost delivery or post a manual GL adjustment to match the LCV-updated rate</td>
							</tr>
							<tr>
								<td>Bin vs Stock GL ❌</td>
								<td>A voucher was cancelled but its GL Entry was not reversed.</td>
								<td>GL Entry report → filter cancelled=Yes → identify orphan → post reversal journal</td>
							</tr>
							<tr>
								<td>Item Variance ≠ 0</td>
								<td>A Stock Entry or Purchase Receipt was partially cancelled — SLE rows are inconsistent.</td>
								<td>Stock Ledger → filter to item → find entry with no matching reverse → cancel and repost</td>
							</tr>
							<tr>
								<td>Local PR = 0 despite purchases</td>
								<td>Company default currency not set, or PR was posted in unexpected currency.</td>
								<td>Check Company → Default Currency; verify Purchase Receipt currency field</td>
							</tr>
							<tr>
								<td>Opening ≠ prior Closing</td>
								<td>A backdated entry was posted after the prior period was reviewed.</td>
								<td>Check audit log for backdated vouchers; use Period Closing Voucher to lock prior period</td>
							</tr>
							<tr>
								<td>Transfer In ≠ Transfer Out</td>
								<td>Transfer involved a Transit warehouse excluded from the filter, or was partially cancelled.</td>
								<td>Remove Warehouse filter and re-run — both sides of the transfer become visible</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>

			<!-- Checklist -->
			<div class="ag-section">
				<h2 class="ag-h2">Period-End Sign-Off Checklist</h2>
				<p class="ag-h2-sub">All items must be confirmed before closing the period.</p>

				<ul class="ag-checklist">

					<li class="ag-cl-group"><div class="ag-box"></div>Audit Trading Account Report</li>

					<li><div class="ag-box"></div><span><strong>COGS Variance = 0.00</strong> — row shows ✅ green. Formula COGS equals perpetual GL COGS.</span></li>
					<li><div class="ag-box"></div><span><strong>Bin vs Stock Account GL = 0.00</strong> — row shows ✅ green. Live inventory matches the balance sheet stock account.</span></li>
					<li><div class="ag-box"></div><span><strong>NET COGS (Trading Formula)</strong> agrees with <strong>NET COGS (Trial Balance)</strong>. Anything under Reconciliation to Trial Balance has a documented explanation.</span></li>
					<li><div class="ag-box"></div><span><strong>Net Sales</strong> ties to Sales Register total for the period.</span></li>
					<li><div class="ag-box"></div><span><strong>Total Purchases</strong> (Local PR + Import PR + LCV) ties to Purchase Receipt totals for the period. PI Rate Adj separately ties to Purchase Invoices where rate differs from the receipt.</span></li>
					<li><div class="ag-box"></div><span><strong>Closing Stock</strong> matches Stock Balance report run on the to-date.</span></li>

					<li class="ag-cl-group"><div class="ag-box"></div>Item COGS Analysis Report</li>

					<li><div class="ag-box"></div><span><strong>No item has Variance ≠ 0</strong> — all Variance ✓ cells show green. Stock equation balances for every item.</span></li>
					<li><div class="ag-box"></div><span><strong>No item has COGS Diff ≠ 0</strong> — all COGS Diff cells show green. SLE COGS = GL COGS for every item.</span></li>
					<li><div class="ag-box"></div><span><strong>Transfer In = Transfer Out</strong> (TOTAL row) across all warehouses company-wide.</span></li>
					<li><div class="ag-box"></div><span><strong>Opening this period = Closing prior period</strong> verified for top 10 items by value.</span></li>

					<li class="ag-cl-group"><div class="ag-box"></div>Period Closure</li>

					<li><div class="ag-box"></div><span><strong>Period Closing Voucher</strong> posted in ERPNext to lock the period against backdated entries.</span></li>
					<li><div class="ag-box"></div><span><strong>Report PDFs archived</strong> with working papers for this period.</span></li>

				</ul>
			</div>

		</div>
	`);
};
