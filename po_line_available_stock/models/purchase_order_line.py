# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    pls_qty_on_hand = fields.Float(
        string="On Hand",
        compute="_compute_pls_stock",
        digits="Product Unit of Measure",
        help="Quantity on hand in the configured inventory scope, "
             "expressed in this line's unit of measure.",
    )
    pls_qty_forecasted = fields.Float(
        string="Forecasted",
        compute="_compute_pls_stock",
        digits="Product Unit of Measure",
        help="Forecasted quantity (on hand + incoming - outgoing) in the "
             "configured inventory scope, expressed in this line's unit "
             "of measure.",
    )
    pls_is_storable = fields.Boolean(
        string="Storable Product", compute="_compute_pls_stock")

    # ------------------------------------------------------------------
    # Scope resolution
    # ------------------------------------------------------------------
    def _pls_scope_warehouses(self, company, warehouses_by_company):
        """Return the warehouse ids that define this line's stock scope.

        ``warehouses_by_company`` is a per-call cache so company-wide scope
        costs one search per company, whatever the number of lines.
        """
        self.ensure_one()
        if company.po_stock_scope == "warehouse":
            warehouse = self.order_id.picking_type_id.warehouse_id
            if warehouse:
                return (warehouse.id,)
            # Dropship / no receiving warehouse: fall back to company-wide
        if company.id not in warehouses_by_company:
            warehouses_by_company[company.id] = tuple(
                self.env["stock.warehouse"].with_context(active_test=True)
                .search([("company_id", "=", company.id)]).ids
            )
        return warehouses_by_company[company.id]

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends(
        "product_id",
        "product_uom",
        "order_id.picking_type_id",
        "order_id.company_id",
        "order_id.company_id.po_stock_visibility",
        "order_id.company_id.po_stock_metric",
        "order_id.company_id.po_stock_scope",
    )
    @api.depends_context("company")
    def _compute_pls_stock(self):
        """Batched stock lookup.

        Lines are grouped by (company, warehouse scope). Each group triggers
        a single ``_compute_quantities_dict`` call for all its products, so
        the number of SQL queries depends on the number of distinct scopes,
        never on the number of lines.
        """
        groups = defaultdict(lambda: self.browse())
        warehouses_by_company = {}

        for line in self:
            line.pls_qty_on_hand = 0.0
            line.pls_qty_forecasted = 0.0
            product = line.product_id
            line.pls_is_storable = bool(product) and product.type == "product"
            company = line.order_id.company_id or line.company_id or self.env.company
            if not company.po_stock_visibility or not line.pls_is_storable:
                continue
            wh_ids = line._pls_scope_warehouses(company, warehouses_by_company)
            if not wh_ids:
                continue
            groups[(company.id, wh_ids)] |= line

        for (company_id, wh_ids), lines in groups.items():
            products = lines.product_id._origin
            stock = (
                products.with_company(company_id)
                .with_context(warehouse=list(wh_ids), location=False)
                ._compute_quantities_dict(None, None, None)
            )
            for line in lines:
                values = stock.get(line.product_id._origin.id)
                if not values:
                    continue
                on_hand = values["qty_available"]
                forecast = values["virtual_available"]
                product_uom = line.product_id.uom_id
                line_uom = line.product_uom
                if line_uom and line_uom != product_uom:
                    on_hand = product_uom._compute_quantity(
                        on_hand, line_uom, round=False,
                        raise_if_failure=False)
                    forecast = product_uom._compute_quantity(
                        forecast, line_uom, round=False,
                        raise_if_failure=False)
                line.pls_qty_on_hand = on_hand
                line.pls_qty_forecasted = forecast
