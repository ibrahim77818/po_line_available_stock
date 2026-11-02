# -*- coding: utf-8 -*-
import logging

from odoo.tests import Form, TransactionCase, tagged


_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install", "po_line_available_stock")
class TestPoLineAvailableStock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.Quant = cls.env["stock.quant"]
        cls.uom_unit = cls.env.ref("uom.product_uom_unit")
        cls.uom_dozen = cls.env.ref("uom.product_uom_dozen")
        cls.vendor = cls.env["res.partner"].create({"name": "PLS Vendor"})

        cls.wh1 = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1)
        cls.wh2 = cls.env["stock.warehouse"].create({
            "name": "PLS Second Warehouse", "code": "PLS2",
            "company_id": cls.company.id,
        })
        cls.customer_loc = cls.env.ref("stock.stock_location_customers")

        cls.product = cls._make_product("PLS Storable")
        cls.consumable = cls.env["product.product"].create({
            "name": "PLS Consumable", "type": "consu",
        })
        # WH1: 10 on hand, WH2: 25 on hand
        cls._add_stock(cls.product, cls.wh1, 10)
        cls._add_stock(cls.product, cls.wh2, 25)

        cls._configure(True, "both", "warehouse")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @classmethod
    def _make_product(cls, name):
        return cls.env["product.product"].create({
            "name": name, "type": "product",
            "uom_id": cls.uom_unit.id, "uom_po_id": cls.uom_unit.id,
        })

    @classmethod
    def _add_stock(cls, product, warehouse, qty):
        cls.Quant.with_company(warehouse.company_id)._update_available_quantity(
            product, warehouse.lot_stock_id, qty)

    @classmethod
    def _configure(cls, enabled, metric, scope, company=None):
        (company or cls.company).write({
            "po_stock_visibility": enabled,
            "po_stock_metric": metric,
            "po_stock_scope": scope,
        })

    def _make_po(self, warehouse, lines, picking_type=None, company=None):
        company = company or self.company
        return self.env["purchase.order"].with_company(company).create({
            "partner_id": self.vendor.id,
            "company_id": company.id,
            "picking_type_id": (picking_type or warehouse.in_type_id).id,
            "order_line": [(0, 0, {
                "product_id": product.id,
                "product_qty": qty,
                "product_uom": (uom or product.uom_po_id).id,
                "price_unit": 1.0,
            }) for product, qty, uom in lines],
        })

    def _ship_out(self, product, warehouse, qty):
        """Confirmed outgoing move: lowers the forecast, not the on hand."""
        move = self.env["stock.move"].create({
            "name": "PLS out",
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": qty,
            "location_id": warehouse.lot_stock_id.id,
            "location_dest_id": self.customer_loc.id,
            "company_id": warehouse.company_id.id,
        })
        move._action_confirm()
        return move

    def _count_queries(self, orders, fnames):
        """Queries needed to compute ``fnames`` on all lines of ``orders``
        from a cold cache, the way the web client reads them."""
        self.env.invalidate_all()
        before = self.cr.sql_log_count
        orders.order_line.mapped(lambda r: [r[f] for f in fnames])
        return self.cr.sql_log_count - before

    # ------------------------------------------------------------------
    # accuracy
    # ------------------------------------------------------------------
    def test_01_warehouse_scope_on_hand(self):
        po1 = self._make_po(self.wh1, [(self.product, 1, None)])
        po2 = self._make_po(self.wh2, [(self.product, 1, None)])
        self.assertEqual(po1.order_line.pls_qty_on_hand, 10)
        self.assertEqual(po2.order_line.pls_qty_on_hand, 25)

    def test_02_company_scope_sums_all_warehouses(self):
        self._configure(True, "both", "company")
        po = self._make_po(self.wh1, [(self.product, 1, None)])
        self.assertEqual(po.order_line.pls_qty_on_hand, 35)

    def test_03_forecast_includes_outgoing_and_incoming(self):
        self._ship_out(self.product, self.wh1, 4)
        po = self._make_po(self.wh1, [(self.product, 7, None)])
        line = po.order_line
        self.assertEqual(line.pls_qty_on_hand, 10)
        self.assertEqual(line.pls_qty_forecasted, 6)
        # Confirming the PO creates an incoming receipt in WH1
        po.button_confirm()
        line.invalidate_recordset()
        self.assertEqual(line.pls_qty_on_hand, 10)
        self.assertEqual(line.pls_qty_forecasted, 13)
        # WH2's forecast is untouched by WH1 moves
        po2 = self._make_po(self.wh2, [(self.product, 1, None)])
        self.assertEqual(po2.order_line.pls_qty_forecasted, 25)

    def test_04_forecast_company_scope(self):
        self._configure(True, "forecast", "company")
        self._ship_out(self.product, self.wh2, 5)
        po = self._make_po(self.wh1, [(self.product, 1, None)])
        self.assertEqual(po.order_line.pls_qty_forecasted, 30)

    def test_05_uom_conversion_to_line_uom(self):
        self._add_stock(self.product, self.wh1, 14)  # 24 units in WH1
        po = self._make_po(self.wh1, [(self.product, 1, self.uom_dozen)])
        self.assertAlmostEqual(po.order_line.pls_qty_on_hand, 2.0)
        self.assertAlmostEqual(po.order_line.pls_qty_forecasted, 2.0)

    def test_06_non_storable_and_disabled(self):
        po = self._make_po(self.wh1, [(self.consumable, 1, None),
                                      (self.product, 1, None)])
        consu_line, stock_line = po.order_line
        self.assertFalse(consu_line.pls_is_storable)
        self.assertEqual(consu_line.pls_qty_on_hand, 0)
        self.assertTrue(stock_line.pls_is_storable)

        self._configure(False, "both", "warehouse")
        po.invalidate_recordset()
        po.order_line.invalidate_recordset()
        self.assertEqual(stock_line.pls_qty_on_hand, 0)
        self.assertFalse(po.pls_show_on_hand)
        self.assertFalse(po.pls_show_forecast)

    def test_07_metric_column_flags(self):
        po = self._make_po(self.wh1, [(self.product, 1, None)])
        for metric, on_hand, forecast in (("on_hand", True, False),
                                          ("forecast", False, True),
                                          ("both", True, True)):
            self._configure(True, metric, "warehouse")
            po.invalidate_recordset()
            self.assertEqual(po.pls_show_on_hand, on_hand, metric)
            self.assertEqual(po.pls_show_forecast, forecast, metric)

    def test_08_no_receiving_warehouse_falls_back_to_company(self):
        dropship_type = self.env["stock.picking.type"].create({
            "name": "PLS Dropship", "code": "incoming",
            "sequence_code": "PLSDS", "warehouse_id": False,
            "company_id": self.company.id,
            "default_location_dest_id": self.customer_loc.id,
        })
        po = self._make_po(self.wh1, [(self.product, 1, None)],
                           picking_type=dropship_type)
        self.assertEqual(po.order_line.pls_qty_on_hand, 35)

    def test_09_multi_company_isolation(self):
        company_b = self.env["res.company"].create({"name": "PLS Company B"})
        wh_b = self.env["stock.warehouse"].search(
            [("company_id", "=", company_b.id)], limit=1)
        self.assertTrue(wh_b, "stock should create a warehouse for company B")
        self._add_stock(self.product, wh_b, 500)

        self._configure(True, "both", "company")
        po = self._make_po(self.wh1, [(self.product, 1, None)])
        # Even with both companies allowed, company A only sees its own stock
        po_line = po.order_line.with_context(
            allowed_company_ids=[self.company.id, company_b.id])
        self.assertEqual(po_line.pls_qty_on_hand, 35)

        self._configure(True, "both", "company", company=company_b)
        po_b = self._make_po(wh_b, [(self.product, 1, None)], company=company_b)
        self.assertEqual(
            po_b.order_line.with_company(company_b).pls_qty_on_hand, 500)

    def test_10_mixed_batch_across_warehouses(self):
        """One recordset spanning warehouses still gets per-line scope."""
        p2 = self._make_product("PLS Second")
        self._add_stock(p2, self.wh1, 3)
        self._add_stock(p2, self.wh2, 8)
        po1 = self._make_po(self.wh1, [(self.product, 1, None), (p2, 1, None)])
        po2 = self._make_po(self.wh2, [(self.product, 1, None), (p2, 1, None)])
        self.env.invalidate_all()
        lines = (po1 | po2).order_line
        got = {(l.order_id.id, l.product_id.id): l.pls_qty_on_hand for l in lines}
        self.assertEqual(got, {
            (po1.id, self.product.id): 10, (po1.id, p2.id): 3,
            (po2.id, self.product.id): 25, (po2.id, p2.id): 8,
        })

    # ------------------------------------------------------------------
    # UI / onchange
    # ------------------------------------------------------------------
    def test_11_form_recomputes_on_warehouse_change(self):
        form = Form(self.env["purchase.order"])
        form.partner_id = self.vendor
        form.picking_type_id = self.wh1.in_type_id
        with form.order_line.new() as line:
            line.product_id = self.product
            self.assertEqual(line.pls_qty_on_hand, 10)
        form.picking_type_id = self.wh2.in_type_id
        with form.order_line.edit(0) as line:
            self.assertEqual(line.pls_qty_on_hand, 25)
            line.product_uom = self.uom_dozen
            # form values are rounded to the field's digits
            self.assertAlmostEqual(line.pls_qty_on_hand, 25 / 12, places=2)
            line.product_id = self.consumable
            self.assertEqual(line.pls_qty_on_hand, 0)

    def test_12_settings_write_company_fields(self):
        settings = self.env["res.config.settings"].create({
            "po_stock_visibility": True,
            "po_stock_metric": "forecast",
            "po_stock_scope": "company",
        })
        settings.execute()
        self.assertTrue(self.company.po_stock_visibility)
        self.assertEqual(self.company.po_stock_metric, "forecast")
        self.assertEqual(self.company.po_stock_scope, "company")

    def test_13_purchase_user_without_inventory_rights(self):
        buyer = self.env["res.users"].create({
            "name": "PLS Buyer", "login": "pls_buyer",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id,
                                  self.env.ref("purchase.group_purchase_user").id])],
        })
        self.assertFalse(buyer.has_group("stock.group_stock_user"))
        self._ship_out(self.product, self.wh1, 4)
        po = self._make_po(self.wh1, [(self.product, 1, None)])
        self.env.invalidate_all()
        line = po.with_user(buyer).order_line
        self.assertEqual(line.pls_qty_on_hand, 10)
        self.assertEqual(line.pls_qty_forecasted, 6)

    # ------------------------------------------------------------------
    # performance
    # ------------------------------------------------------------------
    def test_20_query_count_independent_of_line_count(self):
        products = self.env["product.product"]
        for i in range(40):
            products |= self._make_product("PLS Bulk %s" % i)
        for i, product in enumerate(products):
            self._add_stock(product, self.wh1 if i % 2 else self.wh2, i + 1)
        fnames = ["pls_qty_on_hand", "pls_qty_forecasted"]

        small = self._make_po(self.wh1, [(p, 1, None) for p in products[:3]])
        big = self._make_po(self.wh1, [(p, 1, None) for p in products])
        q_small = self._count_queries(small, fnames)
        q_big = self._count_queries(big, fnames)
        _logger.info("PO line stock: 3 lines -> %s queries, 40 lines -> %s queries",
                     q_small, q_big)
        self.assertLessEqual(
            q_big, q_small,
            "3 lines: %s queries, 40 lines: %s queries" % (q_small, q_big))

        # Values are still per-product correct in the batched path
        for line in big.order_line:
            idx = products.ids.index(line.product_id.id)
            expected = (idx + 1) if idx % 2 else 0
            self.assertEqual(line.pls_qty_on_hand, expected)

    def test_21_query_count_scales_with_scopes_not_lines(self):
        wh3 = self.env["stock.warehouse"].create({
            "name": "PLS Third", "code": "PLS3", "company_id": self.company.id,
        })
        products = self.env["product.product"]
        for i in range(20):
            products |= self._make_product("PLS Multi %s" % i)
        for wh in (self.wh1, self.wh2, wh3):
            for product in products:
                self._add_stock(product, wh, 2)
        fnames = ["pls_qty_on_hand", "pls_qty_forecasted"]

        few = self.env["purchase.order"]
        many = self.env["purchase.order"]
        for wh in (self.wh1, self.wh2, wh3):
            few |= self._make_po(wh, [(p, 1, None) for p in products[:2]])
            many |= self._make_po(wh, [(p, 1, None) for p in products])
        q_few = self._count_queries(few, fnames)
        q_many = self._count_queries(many, fnames)
        _logger.info("PO line stock, 3 warehouses: 6 lines -> %s queries, "
                     "60 lines -> %s queries", q_few, q_many)
        self.assertLessEqual(
            q_many, q_few,
            "6 lines: %s queries, 60 lines: %s queries" % (q_few, q_many))
        self.assertTrue(all(l.pls_qty_on_hand == 2 for l in many.order_line))
