# -*- coding: utf-8 -*-
{
    "name": "PO Line Available Stock",
    "summary": "Show On Hand / Forecasted stock on purchase order lines, "
               "per receiving warehouse or company-wide",
    "description": """
Display live stock levels on purchase order lines.

* Toggle from Purchase settings, per company
* Metric: Quantity On Hand, Forecasted Quantity, or both
* Scope: the PO's receiving warehouse, or all warehouses of the company
* Quantities converted to the purchase line's unit of measure
* Batched computation: query count grows with the number of distinct
  warehouses, not with the number of lines
* Arabic (ar_001) translation, RTL-ready
""",
    "version": "16.0.1.0.0",
    "category": "Inventory/Purchase",
    "author": "Ibrahim Yahia",
    "website": "https://www.linkedin.com/in/ibrahim-yahia",
    "license": "LGPL-3",
    "depends": ["purchase_stock"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/purchase_order_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "po_line_available_stock/static/src/scss/po_line_available_stock.scss",
        ],
    },
    "images": ["static/description/banner.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
