import os
import frappe


def after_migrate():
    sync_pages()
    seed_cash_flow_mappers()
    frappe.db.commit()


def after_install():
    sync_pages()
    seed_cash_flow_mappers()
    frappe.db.commit()


def sync_pages():
    from frappe.modules.import_file import import_file_by_path

    module_dir = frappe.get_app_path("periodic_accounting", "periodic_accounting")
    page_dir = os.path.join(module_dir, "page")
    if not os.path.isdir(page_dir):
        return
    for page_name in os.listdir(page_dir):
        json_path = os.path.join(page_dir, page_name, f"{page_name}.json")
        if os.path.exists(json_path):
            import_file_by_path(json_path, force=True)
            print(f"Synced page: {page_name}")


def seed_cash_flow_mappers():
    """
    Create the three standard Cash Flow Mapper documents and default Cash Flow
    Mapping line-items if they do not already exist.

    Accountants customise these via Periodic Accounting → Cash Flow Mapper.
    The Periodic Cash Flow report uses them when lines are present; otherwise
    it falls back to its hardcoded account-type logic.
    """
    # Use DocType existence (queries tabDocType, always fresh) instead of
    # table_exists (uses a cached list that may not reflect tables just created).
    try:
        if not frappe.db.exists("DocType", "Cash Flow Mapper"):
            print("[periodic_accounting] Cash Flow Mapper DocType not found, skipping seed")
            return
        if not frappe.db.exists("DocType", "Cash Flow Mapping"):
            print("[periodic_accounting] Cash Flow Mapping DocType not found, skipping seed")
            return
    except Exception as e:
        print(f"[periodic_accounting] seed_cash_flow_mappers: DocType check failed: {e}")
        return

    frappe.set_user("Administrator")

    _ensure_mapping("Depreciation Add-back",
        label="Add: Depreciation",
        calculation_type="GL: debit minus credit",
        is_working_capital=0,
        accounts="",
    )
    _ensure_mapping("Receivables Change",
        label="(Increase) / Decrease in Trade Receivables",
        calculation_type="GL: credit minus debit",
        is_working_capital=1,
        accounts="",
    )
    _ensure_mapping("Payables Change",
        label="Increase / (Decrease) in Trade Payables",
        calculation_type="GL: credit minus debit",
        is_working_capital=1,
        accounts="",
    )
    _ensure_mapping("Inventory Change",
        label="(Increase) / Decrease in Inventory",
        calculation_type="SLE: inventory change",
        is_working_capital=1,
        accounts="",
    )
    _ensure_mapping("Fixed Assets Change",
        label="Net (Purchase) / Sale of Fixed Assets",
        calculation_type="GL: credit minus debit",
        is_working_capital=0,
        accounts="",
    )
    _ensure_mapping("Equity Change",
        label="Net Change in Equity / Capital",
        calculation_type="GL: credit minus debit",
        is_working_capital=0,
        accounts="",
    )
    frappe.db.commit()

    _ensure_mapper(
        section_name="Operating Activities",
        section_leader="Adjustments for Non-Cash Items",
        section_subtotal="Cash from Operations before Working Capital Changes",
        section_footer="Net Cash from Operating Activities",
        mappings=[
            "Depreciation Add-back",
            "Receivables Change",
            "Payables Change",
            "Inventory Change",
        ],
    )
    _ensure_mapper(
        section_name="Investing Activities",
        section_leader="",
        section_subtotal="",
        section_footer="Net Cash from Investing Activities",
        mappings=["Fixed Assets Change"],
    )
    _ensure_mapper(
        section_name="Financing Activities",
        section_leader="",
        section_subtotal="",
        section_footer="Net Cash from Financing Activities",
        mappings=["Equity Change"],
    )
    frappe.db.commit()


def _ensure_mapping(name, label, calculation_type, is_working_capital, accounts):
    if frappe.db.exists("Cash Flow Mapping", name):
        return
    try:
        doc = frappe.new_doc("Cash Flow Mapping")
        doc.mapping_name       = name   # autoname: field:mapping_name
        doc.label              = label
        doc.calculation_type   = calculation_type
        doc.is_working_capital = is_working_capital
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        print(f"[periodic_accounting] Created Cash Flow Mapping: {name}")
    except Exception as e:
        print(f"[periodic_accounting] WARN: could not create Cash Flow Mapping '{name}': {e}")


def _ensure_mapper(section_name, section_leader, section_subtotal, section_footer, mappings):
    if frappe.db.exists("Cash Flow Mapper", section_name):
        return
    try:
        doc = frappe.new_doc("Cash Flow Mapper")
        doc.section_name     = section_name
        doc.section_leader   = section_leader
        doc.section_subtotal = section_subtotal
        doc.section_footer   = section_footer
        for m in mappings:
            doc.append("mapping", {"mapping": m})
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
        print(f"[periodic_accounting] Created Cash Flow Mapper: {section_name}")
    except Exception as e:
        print(f"[periodic_accounting] WARN: could not create Cash Flow Mapper '{section_name}': {e}")
