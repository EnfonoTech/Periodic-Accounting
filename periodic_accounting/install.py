import os
import frappe


def after_migrate():
    sync_pages()
    frappe.db.commit()


def after_install():
    sync_pages()
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
