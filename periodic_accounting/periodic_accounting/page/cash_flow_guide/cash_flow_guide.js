frappe.pages["cash-flow-guide"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Standard Cash Flow Report — Configuration Guide",
		single_column: true,
	});

	$(wrapper).find(".page-content").html(get_guide_html());

	page.add_inner_button(__("Open Cash Flow Report"), function () {
		frappe.set_route("query-report", "Standard Cash Flow Report", {
			company: frappe.defaults.get_user_default("Company"),
		});
	}, __("Open Report"));

	page.add_inner_button(__("Cash Flow Mapping"), function () {
		frappe.set_route("List", "Cash Flow Mapping");
	}, __("Configure"));

	page.add_inner_button(__("Cash Flow Mapper"), function () {
		frappe.set_route("List", "Cash Flow Mapper");
	}, __("Configure"));
};

function get_guide_html() {
	var card  = "background:var(--card-bg,#fff);border:1px solid var(--border-color,#e2e8f0);border-radius:10px;padding:24px 28px;margin-bottom:24px;";
	var h2    = "font-size:1.15em;font-weight:700;margin:0 0 14px;color:var(--heading-color,#1a202c);border-bottom:2px solid var(--primary,#4c85e7);padding-bottom:8px;";
	var h3    = "font-size:1em;font-weight:600;margin:18px 0 6px;color:var(--text-color,#2d3748);";
	var badge = function(text, color) {
		return `<span style="background:${color};color:#fff;font-size:0.78em;font-weight:600;padding:2px 8px;border-radius:4px;margin-right:6px;">${text}</span>`;
	};
	var tbl   = "width:100%;border-collapse:collapse;font-size:0.93em;margin-top:10px;";
	var th    = "text-align:left;padding:8px 12px;background:var(--subtle-fg,#f7fafc);border:1px solid var(--border-color,#e2e8f0);font-weight:600;";
	var td    = "padding:8px 12px;border:1px solid var(--border-color,#e2e8f0);vertical-align:top;";
	var code  = "background:var(--code-bg,#f1f5f9);padding:2px 6px;border-radius:3px;font-family:monospace;font-size:0.9em;";

	return `
<div style="max-width:940px;margin:0 auto;padding:24px 16px;font-family:var(--font-stack);color:var(--text-color,#2d3748);line-height:1.7;">

<!-- ── HEADER ── -->
<div style="background:linear-gradient(135deg,#0d47a1,#1976d2);color:#fff;border-radius:12px;padding:32px 36px;margin-bottom:28px;">
  <h1 style="margin:0 0 8px;font-size:1.75em;font-weight:700;">Standard Cash Flow Report</h1>
  <p style="margin:0;opacity:0.88;font-size:1.05em;">Configuration Guide — Cash Flow Mapper &amp; Cash Flow Mapping</p>
</div>

<!-- ── OVERVIEW ── -->
<div style="${card}">
  <h2 style="${h2}">Overview</h2>
  <p>The <strong>Standard Cash Flow Report</strong> is an indirect-method cash flow statement that is fully configurable via two DocTypes — <strong>Cash Flow Mapping</strong> and <strong>Cash Flow Mapper</strong>.</p>
  <p>The report calculates Net Profit from the GL (Income credit − Expense debit) and adds back non-cash / working-capital adjustments to arrive at operating cash flow, then adds investing and financing activities.</p>
  <table style="${tbl}">
    <thead><tr>
      <th style="${th}">What</th><th style="${th}">Where it lives</th><th style="${th}">Purpose</th>
    </tr></thead>
    <tbody>
      <tr><td style="${td}"><strong>Cash Flow Mapping</strong></td><td style="${td}">Accounting → Cash Flow Mapping</td><td style="${td}">Defines one line item (e.g. "Depreciation Add-back") with its GL accounts and calculation method.</td></tr>
      <tr><td style="${td}"><strong>Cash Flow Mapper</strong></td><td style="${td}">Accounting → Cash Flow Mapper</td><td style="${td}">Groups Mapping lines into a section (Operating / Investing / Financing) and controls section headings and totals.</td></tr>
    </tbody>
  </table>
</div>

<!-- ── CASH FLOW MAPPING ── -->
<div style="${card}">
  <h2 style="${h2}">Step 1 — Create Cash Flow Mapping Docs</h2>
  <p>Each Cash Flow Mapping document represents <strong>one line</strong> in the report (e.g. "Depreciation", "Change in Receivables").</p>

  <h3 style="${h3}">Fields</h3>
  <table style="${tbl}">
    <thead><tr>
      <th style="${th}">Field</th><th style="${th}">Description</th>
    </tr></thead>
    <tbody>
      <tr>
        <td style="${td}"><span style="${code}">Name</span></td>
        <td style="${td}">Unique identifier. Used to reference this mapping from a Mapper. Example: <em>Depreciation Add-back</em></td>
      </tr>
      <tr>
        <td style="${td}"><span style="${code}">Label</span></td>
        <td style="${td}">Text displayed in the report for this line. Example: <em>Add: Depreciation &amp; Amortisation</em></td>
      </tr>
      <tr>
        <td style="${td}"><span style="${code}">Calculation Type</span></td>
        <td style="${td}">How the amount is computed — see Calculation Types below.</td>
      </tr>
      <tr>
        <td style="${td}"><span style="${code}">Is Working Capital</span></td>
        <td style="${td}">Check for receivable / payable / inventory lines. These are grouped under the "Working Capital Changes" sub-heading in Operating Activities.</td>
      </tr>
      <tr>
        <td style="${td}"><span style="${code}">Is Finance Cost</span></td>
        <td style="${td}">Mark if this is a finance cost (e.g. interest expense). Informational — matches the original ERPNext field for compatibility.</td>
      </tr>
      <tr>
        <td style="${td}"><span style="${code}">Is Income Tax Expense</span></td>
        <td style="${td}">Mark if this represents income tax. Informational.</td>
      </tr>
      <tr>
        <td style="${td}"><span style="${code}">Accounts</span> (child table)</td>
        <td style="${td}">Select one or more GL <strong>leaf accounts</strong> whose movements make up this line. Leave empty when Calculation Type is <em>SLE: inventory change</em>.</td>
      </tr>
    </tbody>
  </table>

  <h3 style="${h3}">Calculation Types</h3>
  <table style="${tbl}">
    <thead><tr>
      <th style="${th}">Type</th><th style="${th}">Formula</th><th style="${th}">Use when</th>
    </tr></thead>
    <tbody>
      <tr>
        <td style="${td}">${badge("GL: credit minus debit","#1976d2")} GL: credit minus debit</td>
        <td style="${td}"><span style="${code}">SUM(credit) − SUM(debit)</span></td>
        <td style="${td}">Liability / payable accounts — an increase (credit) represents a cash inflow. Also used for equity.</td>
      </tr>
      <tr>
        <td style="${td}">${badge("GL: debit minus credit","#7b1fa2")} GL: debit minus credit</td>
        <td style="${td}"><span style="${code}">SUM(debit) − SUM(credit)</span></td>
        <td style="${td}">Non-cash expense add-backs like <strong>Depreciation</strong>. A debit to depreciation expense reduces net profit but is not a cash outflow, so we add it back (debit − credit = positive add-back).</td>
      </tr>
      <tr>
        <td style="${td}">${badge("SLE: inventory change","#e65100")} SLE: inventory change</td>
        <td style="${td}"><span style="${code}">Opening Stock − Closing Stock</span></td>
        <td style="${td}">For <strong>non-perpetual inventory</strong> sites where GL stock accounts are not updated. Uses Stock Ledger Entry to compute physical stock movement. Leave the Accounts child table <em>empty</em> for this type.</td>
      </tr>
    </tbody>
  </table>

  <h3 style="${h3}">Common Mapping Examples</h3>
  <table style="${tbl}">
    <thead><tr>
      <th style="${th}">Name</th><th style="${th}">Label</th><th style="${th}">Calculation Type</th><th style="${th}">Is WC</th><th style="${th}">Accounts</th>
    </tr></thead>
    <tbody>
      <tr><td style="${td}">Depreciation Add-back</td><td style="${td}">Add: Depreciation &amp; Amortisation</td><td style="${td}">GL: debit minus credit</td><td style="${td}">No</td><td style="${td}">Depreciation account(s)</td></tr>
      <tr><td style="${td}">Receivables Change</td><td style="${td}">Decrease / (Increase) in Receivables</td><td style="${td}">GL: credit minus debit</td><td style="${td}">Yes</td><td style="${td}">Accounts Receivable, Debtors</td></tr>
      <tr><td style="${td}">Payables Change</td><td style="${td}">Increase / (Decrease) in Payables</td><td style="${td}">GL: credit minus debit</td><td style="${td}">Yes</td><td style="${td}">Accounts Payable, Creditors</td></tr>
      <tr><td style="${td}">Inventory Change</td><td style="${td}">Decrease / (Increase) in Inventory</td><td style="${td}">SLE: inventory change</td><td style="${td}">Yes</td><td style="${td}"><em>leave empty</em></td></tr>
      <tr><td style="${td}">Fixed Assets Change</td><td style="${td}">Purchase / Sale of Fixed Assets</td><td style="${td}">GL: credit minus debit</td><td style="${td}">No</td><td style="${td}">Fixed Asset account(s)</td></tr>
      <tr><td style="${td}">Equity Change</td><td style="${td}">Share Capital / Loan Movements</td><td style="${td}">GL: credit minus debit</td><td style="${td}">No</td><td style="${td}">Equity / Long-term Loan accounts</td></tr>
    </tbody>
  </table>
</div>

<!-- ── CASH FLOW MAPPER ── -->
<div style="${card}">
  <h2 style="${h2}">Step 2 — Configure Cash Flow Mapper</h2>
  <p>A Cash Flow Mapper document defines <strong>one section</strong> of the report. Three mappers are seeded automatically:</p>
  <ul style="margin:8px 0 16px 20px;">
    <li><strong>Operating Activities</strong></li>
    <li><strong>Investing Activities</strong></li>
    <li><strong>Financing Activities</strong></li>
  </ul>
  <p>Open each mapper and use the <strong>Mapping</strong> child table to add the Cash Flow Mapping lines that belong to that section.</p>

  <h3 style="${h3}">Mapper Fields</h3>
  <table style="${tbl}">
    <thead><tr>
      <th style="${th}">Field</th><th style="${th}">Description</th>
    </tr></thead>
    <tbody>
      <tr><td style="${td}"><span style="${code}">Section Name</span></td><td style="${td}">Name of the section. Must be one of: <em>Operating Activities</em>, <em>Investing Activities</em>, <em>Financing Activities</em> for the report to recognise it.</td></tr>
      <tr><td style="${td}"><span style="${code}">Section Leader</span></td><td style="${td}">Optional sub-heading text shown at the top of this section.</td></tr>
      <tr><td style="${td}"><span style="${code}">Section Footer</span></td><td style="${td}">Label for the section total row. E.g. <em>Net Cash from Operating Activities</em>.</td></tr>
      <tr><td style="${td}"><span style="${code}">Section Subtotal</span></td><td style="${td}">Optional mid-section subtotal label.</td></tr>
      <tr><td style="${td}"><span style="${code}">Mapping</span> (child table)</td><td style="${td}">List of Cash Flow Mapping docs that appear in this section, in display order. Optionally override the label for this mapper context using <em>Label Override</em>.</td></tr>
    </tbody>
  </table>
</div>

<!-- ── FALLBACK ── -->
<div style="${card}">
  <h2 style="${h2}">Fallback — When No Mapper Is Configured</h2>
  <p>If the Operating Activities mapper has no mapping lines, the report falls back to ERPNext's hardcoded account-type logic:</p>
  <table style="${tbl}">
    <thead><tr><th style="${th}">Line</th><th style="${th}">Account Type Used</th><th style="${th}">Calculation</th></tr></thead>
    <tbody>
      <tr><td style="${td}">Depreciation</td><td style="${td}">Depreciation</td><td style="${td}">debit − credit</td></tr>
      <tr><td style="${td}">Net Change in Receivables</td><td style="${td}">Receivable</td><td style="${td}">credit − debit</td></tr>
      <tr><td style="${td}">Net Change in Payables</td><td style="${td}">Payable</td><td style="${td}">credit − debit</td></tr>
      <tr><td style="${td}">Net Change in Inventory</td><td style="${td}">Stock</td><td style="${td}">credit − debit</td></tr>
      <tr><td style="${td}">Net Change in Fixed Assets</td><td style="${td}">Fixed Asset</td><td style="${td}">credit − debit</td></tr>
      <tr><td style="${td}">Net Change in Equity</td><td style="${td}">Equity</td><td style="${td}">credit − debit</td></tr>
    </tbody>
  </table>
  <p style="margin-top:12px;">The default seeded mappers (created during install/migrate) already use explicit account lists for better accuracy. Use the fallback only if you delete all mapper lines.</p>
</div>

<!-- ── REPORT FILTERS ── -->
<div style="${card}">
  <h2 style="${h2}">Report Filters</h2>
  <table style="${tbl}">
    <thead><tr><th style="${th}">Filter</th><th style="${th}">Description</th></tr></thead>
    <tbody>
      <tr><td style="${td}">Company</td><td style="${td}">Required. All GL queries are scoped to this company.</td></tr>
      <tr><td style="${td}">Finance Book</td><td style="${td}">Optional. Restricts GL entries to this finance book.</td></tr>
      <tr><td style="${td}">Fiscal Year</td><td style="${td}">Auto-fills From Date and To Date from the selected fiscal year's start and end.</td></tr>
      <tr><td style="${td}">From Date / To Date</td><td style="${td}">The reporting period. All GL activity between these dates is included.</td></tr>
      <tr><td style="${td}">Cost Center</td><td style="${td}">Optional. Filters GL entries to a specific cost center.</td></tr>
      <tr><td style="${td}">Project</td><td style="${td}">Optional. Filters GL entries to a specific project.</td></tr>
      <tr><td style="${td}">Include Default FB Entries</td><td style="${td}">When Finance Book is set, also include GL entries with no finance book assigned (default: checked).</td></tr>
      <tr><td style="${td}">Show Opening and Closing Balance</td><td style="${td}">Appends opening and closing Bank+Cash balances at the bottom of the report.</td></tr>
    </tbody>
  </table>
</div>

<!-- ── DRILL DOWN ── -->
<div style="${card}">
  <h2 style="${h2}">Drill-Down</h2>
  <p>Every individual line in the report is <span style="color:var(--primary,#4c85e7);text-decoration:underline;">underlined and clickable</span>:</p>
  <ul style="margin:8px 0 0 20px;">
    <li><strong>Account-mapped lines</strong> — opens the GL Entry list filtered to the mapped accounts and the selected date range.</li>
    <li><strong>Net Profit / (Loss)</strong> — navigates to the Periodic Gross and Net Profit report for the same period.</li>
  </ul>
</div>


</div>`;
}
