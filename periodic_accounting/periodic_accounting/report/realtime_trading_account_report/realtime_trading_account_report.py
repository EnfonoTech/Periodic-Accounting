import frappe
from frappe import _
from frappe.utils import flt, getdate, today, add_days
from urllib.parse import urlencode


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data    = get_data(filters)
	return columns, data


def get_periodic_gl(filters):
	"""
	When the user supplies a periodic_entry_account filter, query GL entries on that
	COGS account to surface the GL-posted opening and closing stock amounts from
	submitted Periodic Accounting Entries.  Returns (opening_dr, opening_cr,
	period_dr, period_cr) — all floats — or None when the filter is absent.
	"""
	account = filters.get("periodic_entry_account")
	if not account:
		return None

	opening = frappe.db.sql(
		"""SELECT COALESCE(SUM(debit),0) AS dr, COALESCE(SUM(credit),0) AS cr
		   FROM `tabGL Entry`
		   WHERE account = %(account)s AND company = %(company)s
		     AND posting_date < %(from_date)s AND is_cancelled = 0""",
		{**filters, "account": account}, as_dict=True,
	)
	period = frappe.db.sql(
		"""SELECT COALESCE(SUM(debit),0) AS dr, COALESCE(SUM(credit),0) AS cr
		   FROM `tabGL Entry`
		   WHERE account = %(account)s AND company = %(company)s
		     AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		     AND is_cancelled = 0""",
		{**filters, "account": account}, as_dict=True,
	)
	o = opening[0] if opening else frappe._dict(dr=0, cr=0)
	p = period[0]  if period  else frappe._dict(dr=0, cr=0)
	return flt(o.dr), flt(o.cr), flt(p.dr), flt(p.cr)


def get_columns():
	return [
		{"label": _("Particulars"),  "fieldname": "particulars", "fieldtype": "Data",     "width": 340},
		{"label": _("Amount (Dr)"),  "fieldname": "debit",       "fieldtype": "Currency",  "width": 180},
		{"label": _("Amount (Cr)"),  "fieldname": "credit",      "fieldtype": "Currency",  "width": 180},
	]


# ── URL helpers ───────────────────────────────────────────────────────────────

def _url(report, params):
	return f"/app/query-report/{report.replace(' ', '%20')}?{urlencode(params)}"


def _sales_reg(company, from_date, to_date):
	return _url("Sales Register", {"company": company, "from_date": from_date, "to_date": to_date})


def _stock_ledger(company, from_date, to_date, warehouse=None):
	"""Stock Ledger report — the actual source of Gross Purchases / Returns figures (SLE-based)."""
	p = {"company": company, "from_date": from_date, "to_date": to_date}
	if warehouse:
		p["warehouse"] = warehouse
	return _url("Stock Ledger", p)


def _stock_bal(company, as_of_date, warehouse=None):
	p = {"company": company, "date": str(as_of_date)}
	if warehouse:
		p["warehouse"] = warehouse
	return _url("Stock Balance", p)


# ── Data helpers ──────────────────────────────────────────────────────────────

def get_opening_stock(filters):
	"""Cumulative SLE stock_value before period start"""
	conditions = "sle.company = %(company)s AND sle.posting_date < %(from_date)s AND sle.is_cancelled = 0"
	if filters.get("warehouse"):
		conditions += " AND sle.warehouse = %(warehouse)s"
	result = frappe.db.sql(
		f"""SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS val
		    FROM `tabStock Ledger Entry` sle WHERE {conditions}""",
		filters, as_dict=True,
	)
	return flt(result[0].val) if result else 0.0


def get_closing_stock_live(filters):
	"""Live closing stock — tabBin when to_date >= today, else cumulative SLE."""
	if getdate(filters.get("to_date")) >= getdate(today()):
		conditions = "w.company = %(company)s AND b.actual_qty > 0"
		if filters.get("warehouse"):
			conditions += " AND b.warehouse = %(warehouse)s"
		result = frappe.db.sql(
			f"""SELECT COALESCE(SUM(b.actual_qty * b.valuation_rate), 0) AS val
			    FROM `tabBin` b
			    INNER JOIN `tabWarehouse` w ON w.name = b.warehouse
			    WHERE {conditions}""",
			filters, as_dict=True,
		)
	else:
		conditions = "sle.company = %(company)s AND sle.posting_date <= %(to_date)s AND sle.is_cancelled = 0"
		if filters.get("warehouse"):
			conditions += " AND sle.warehouse = %(warehouse)s"
		result = frappe.db.sql(
			f"""SELECT COALESCE(SUM(sle.stock_value_difference), 0) AS val
			    FROM `tabStock Ledger Entry` sle WHERE {conditions}""",
			filters, as_dict=True,
		)
	return flt(result[0].val) if result else 0.0


def get_purchases(filters):
	"""
	Stock value inflows from SLE for the period:
	  - Purchase Invoice / Purchase Receipt  (local + import; returns = negative SLE)
	  - Landed Cost Voucher                  (freight, customs, other landed costs)
	Gross  = sum of positive SLE changes  (purchases + LCV allocations)
	Returns = abs sum of negative SLE changes (purchase returns / debit notes)
	"""
	conditions = """
		sle.company = %(company)s
		AND sle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		AND sle.voucher_type IN (
		    'Purchase Invoice',
		    'Purchase Receipt',
		    'Landed Cost Voucher'
		)
		AND sle.is_cancelled = 0
	"""
	if filters.get("warehouse"):
		conditions += " AND sle.warehouse = %(warehouse)s"
	result = frappe.db.sql(
		f"""SELECT
			    COALESCE(SUM(CASE WHEN sle.stock_value_difference > 0
			        THEN sle.stock_value_difference ELSE 0 END), 0) AS gross,
			    COALESCE(ABS(SUM(CASE WHEN sle.stock_value_difference < 0
			        THEN sle.stock_value_difference ELSE 0 END)), 0) AS returns
			FROM `tabStock Ledger Entry` sle
			WHERE {conditions}""",
		filters, as_dict=True,
	)
	if result:
		g = flt(result[0].gross)
		r = flt(result[0].returns)
		return g, r, g - r
	return 0.0, 0.0, 0.0


def get_sales(filters):
	"""GL credits on Income accounts from Sales Invoices & Delivery Notes"""
	conditions = """
		gle.company = %(company)s
		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		AND gle.voucher_type IN ('Sales Invoice', 'Delivery Note')
		AND gle.is_cancelled = 0
		AND acc.root_type    = 'Income'
		AND acc.account_type = 'Income Account'
	"""
	result = frappe.db.sql(
		f"""SELECT
			    COALESCE(SUM(gle.credit), 0) AS gross,
			    COALESCE(SUM(gle.debit),  0) AS returns
			FROM `tabGL Entry` gle
			INNER JOIN `tabAccount` acc ON acc.name = gle.account
			WHERE {conditions}""",
		filters, as_dict=True,
	)
	if result:
		g = flt(result[0].gross)
		r = flt(result[0].returns)
		return g, r, g - r
	return 0.0, 0.0, 0.0


# ── Main data builder ─────────────────────────────────────────────────────────

def get_data(filters):
	opening_stock                         = get_opening_stock(filters)
	closing_stock                         = get_closing_stock_live(filters)
	gross_pur, pur_returns, net_purchases = get_purchases(filters)
	gross_sales, sal_returns, net_sales   = get_sales(filters)

	cogs         = opening_stock + net_purchases - closing_stock
	gross_profit = net_sales - cogs

	co = filters.company
	fd = str(filters.from_date)
	td = str(filters.to_date)
	wh = filters.get("warehouse")

	opening_date = str(add_days(fd, -1))

	def row(particulars, debit=0, credit=0, bold=False, indent=0, link=None):
		return {
			"particulars": particulars,
			"debit":       debit,
			"credit":      credit,
			"bold":        bold,
			"indent":      indent,
			"link":        link,
		}

	def spacer():
		return row("", 0, 0)

	rows = [
		# ── SALES ──────────────────────────────────────────────────────────
		row("SALES", bold=True),
		row("Gross Sales Revenue",
		    credit=gross_sales, indent=1,
		    link=_sales_reg(co, fd, td)),
		row("Less: Sales Returns",
		    debit=sal_returns, indent=1,
		    link=_sales_reg(co, fd, td)),
		row("NET SALES REVENUE",
		    credit=net_sales, bold=True),
		spacer(),

		# ── COST OF GOODS SOLD ─────────────────────────────────────────────
		row("COST OF GOODS SOLD", bold=True),
		row("Opening Stock",
		    debit=opening_stock, indent=1,
		    link=_stock_bal(co, opening_date, wh)),
		row("Add: Gross Purchases",
		    debit=gross_pur, indent=1,
		    link=_stock_ledger(co, fd, td, wh)),
		row("Less: Purchase Returns",
		    credit=pur_returns, indent=1,
		    link=_stock_ledger(co, fd, td, wh)),
		row("Net Purchases",
		    debit=net_purchases, bold=True),
		row("Goods Available for Sale",
		    debit=opening_stock + net_purchases, indent=1),
		row("Less: Closing Stock",
		    credit=closing_stock, indent=1,
		    link=_stock_bal(co, td, wh)),
		row("NET COGS",
		    debit=cogs, bold=True),
		spacer(),

		# ── GROSS PROFIT ───────────────────────────────────────────────────
		row("GROSS PROFIT",
		    debit=gross_profit  if gross_profit  < 0 else 0,
		    credit=gross_profit if gross_profit >= 0 else 0,
		    bold=True),
	]

	# ── GL RECONCILIATION (shown only when periodic_entry_account is set) ──
	gl = get_periodic_gl(filters)
	if gl is not None:
		open_dr, open_cr, period_dr, period_cr = gl
		# New accountant's approach:
		#   Opening Stock JE → Dr on COGS a/c (opening stock cost, at period start)
		#   Closing JE       → Dr on COGS a/c (net COGS), Cr on Purchases a/c
		# Net COGS on Periodic Entry Diff = period_dr (COGS this period)
		# Opening stock already expensed   = open_dr (prior period closing stock)
		gl_cogs = flt(period_dr)
		gl_opening = flt(open_dr)
		rows += [
			spacer(),
			row("PERIODIC ENTRY RECONCILIATION (GL)", bold=True),
			row("Opening Stock — GL (Dr on COGS a/c before period start)",
			    debit=gl_opening, indent=1),
			row("Net COGS — GL (Dr on COGS a/c during period)",
			    debit=gl_cogs, indent=1),
			row("Total Cost (Opening + COGS) — GL",
			    debit=gl_opening + gl_cogs, bold=True),
			row("SLE Opening Stock (should match GL opening above)",
			    debit=opening_stock, indent=1),
			row("SLE Closing Stock / Bin (for reference)",
			    credit=closing_stock, indent=1),
			row("SLE Net COGS (Opening + Purchases − Closing)",
			    debit=cogs, bold=True),
		]

	return rows
