# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    po_stock_visibility = fields.Boolean(
        related="company_id.po_stock_visibility", readonly=False,
    )
    po_stock_metric = fields.Selection(
        related="company_id.po_stock_metric", readonly=False,
    )
    po_stock_scope = fields.Selection(
        related="company_id.po_stock_scope", readonly=False,
    )
