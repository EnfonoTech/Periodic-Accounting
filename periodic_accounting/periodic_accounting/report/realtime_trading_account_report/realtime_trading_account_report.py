import frappe
from frappe import _
from frappe.utils import flt, getdate, today, add_days
from urllib.parse import urlencode


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data    = get_data(filters)
	return columns, data


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


def _pur_reg(company, from_date, to_date):
	return _url("Purchase Register", {"company": company, "from_date": from_date, "to_date": to_date})


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
	"""GL debits on COGS / Valuation accounts from Purchase Invoices & Receipts"""
	conditions = """
		gle.company = %(company)s
		AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		AND gle.voucher_type IN ('Purchase Invoice', 'Purchase Receipt')
		AND gle.is_cancelled = 0
		AND acc.root_type = 'Expense'
		AND acc.account_type IN ('Cost of Goods Sold', 'Expenses Included In Valuation')
	"""
	result = frappe.db.sql(
		f"""SELECT
			    COALESCE(SUM(gle.debit),  0) AS gross,
			    COALESCE(SUM(gle.credit), 0) AS returns
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

	return [
		# ── SALES ──────────────────────────────────────────────────────────
		row("SALES", bold=True),
		row("Gross Sales Revenue",
		    credit=gross_sales, indent=1,
		    link=_sales_reg(co, fd, td)),
		row("Less: Sales Returns",
		    debit=sal_returns, indent=1,
		    link=_sales_reg(co, fd, td)),
		row("Net Sales Revenue",
		    credit=net_sales, bold=True),
		spacer(),

		# ── COST OF SALES ───────────────────────────────────────────────────
		row("COST OF SALES", bold=True),
		row("Opening Stock",
		    debit=opening_stock, indent=1,
		    link=_stock_bal(co, opening_date, wh)),
		row("Add: Gross Purchases",
		    debit=gross_pur, indent=1,
		    link=_pur_reg(co, fd, td)),
		row("Less: Purchase Returns",
		    credit=pur_returns, indent=1,
		    link=_pur_reg(co, fd, td)),
		row("Net Purchases",
		    debit=net_purchases, bold=True),
		spacer(),
		row("Goods Available for Sale",
		    debit=opening_stock + net_purchases, indent=1),
		row("Less: Closing Stock (Live)",
		    credit=closing_stock, indent=1,
		    link=_stock_bal(co, td, wh)),
		spacer(),

		# ── COGS & GP ───────────────────────────────────────────────────────
		row("COST OF GOODS SOLD",
		    debit=cogs, bold=True),
		spacer(),
		row("GROSS PROFIT",
		    debit=gross_profit  if gross_profit  < 0 else 0,
		    credit=gross_profit if gross_profit >= 0 else 0,
		    bold=True),
	]
