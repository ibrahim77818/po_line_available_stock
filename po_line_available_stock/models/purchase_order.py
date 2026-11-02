# -*- coding: utf-8 -*-
from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    # Column-visibility flags read by the order line list
    # (``column_invisible`` on ``parent.*``). Not stored: they follow the
    # company settings live.
    pls_show_on_hand = fields.Boolean(
        string="Show On Hand Column", compute="_compute_pls_show")
    pls_show_forecast = fields.Boolean(
        string="Show Forecast Column", compute="_compute_pls_show")

    @api.depends(
        "company_id.po_stock_visibility",
        "company_id.po_stock_metric",
    )
    def _compute_pls_show(self):
        for order in self:
            company = order.company_id or self.env.company
            enabled = company.po_stock_visibility
            metric = company.po_stock_metric
            order.pls_show_on_hand = enabled and metric in ("on_hand", "both")
            order.pls_show_forecast = enabled and metric in ("forecast", "both")
