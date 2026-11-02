# -*- coding: utf-8 -*-
from odoo import fields, models

METRIC_SELECTION = [
    ("on_hand", "Quantity On Hand"),
    ("forecast", "Forecasted Quantity"),
    ("both", "Both"),
]

SCOPE_SELECTION = [
    ("warehouse", "PO Warehouse Only"),
    ("company", "All Company Warehouses"),
]


class ResCompany(models.Model):
    _inherit = "res.company"

    po_stock_visibility = fields.Boolean(
        string="Stock on PO Lines",
        help="Show stock levels on purchase order lines.",
    )
    po_stock_metric = fields.Selection(
        METRIC_SELECTION,
        string="Stock Metric",
        default="both",
        required=True,
    )
    po_stock_scope = fields.Selection(
        SCOPE_SELECTION,
        string="Inventory Scope",
        default="warehouse",
        required=True,
    )
