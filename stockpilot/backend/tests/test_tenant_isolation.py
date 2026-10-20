from django.test import TestCase

from apps.catalog.models import Category, Product
from apps.inventory.services.ledger import post_movement

from .helpers import client_for, main_location, make_org, make_product, post_move


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.org_a, self.owner_a = make_org("A", "a@a.test")
        self.org_b, self.owner_b = make_org("B", "b@b.test")
        self.prod_a = make_product(self.org_a, "SKU-A")
        self.prod_b = make_product(self.org_b, "SKU-B")
        post_movement(org=self.org_b, product=self.prod_b, location=main_location(self.org_b), qty_delta=5,
                      movement_type="RECEIPT", idempotency_key="b-1")
        self.a = client_for(self.owner_a, self.org_a)

    def test_list_only_returns_own_products(self):
        skus = {r["sku"] for r in self.a.get("/api/v1/products/").data["results"]}
        self.assertEqual(skus, {"SKU-A"})

    def test_cannot_read_modify_or_archive_foreign_product(self):
        url = f"/api/v1/products/{self.prod_b.id}/"
        self.assertEqual(self.a.get(url).status_code, 404)
        self.assertEqual(self.a.patch(url, {"name": "x"}, format="json").status_code, 404)
        self.assertEqual(self.a.delete(url).status_code, 404)
        self.prod_b.refresh_from_db()
        self.assertFalse(self.prod_b.is_archived)

    def test_cannot_post_movement_against_foreign_product_or_location(self):
        res = post_move(self.a, self.prod_b, main_location(self.org_a), 1, "RECEIPT", "x-1")
        self.assertEqual(res.status_code, 400)
        res = post_move(self.a, self.prod_a, main_location(self.org_b), 1, "RECEIPT", "x-2")
        self.assertEqual(res.status_code, 400)

    def test_foreign_organisation_header_is_forbidden(self):
        c = client_for(self.owner_a)
        c.credentials(HTTP_X_ORGANISATION_ID=str(self.org_b.id))
        self.assertEqual(c.get("/api/v1/products/").status_code, 403)
        c.credentials(HTTP_X_ORGANISATION_ID="not-a-uuid")
        self.assertEqual(c.get("/api/v1/products/").status_code, 403)

    def test_foreign_category_rejected_on_product_create(self):
        cat_b = Category.objects.create(organisation=self.org_b, name="Secret")
        res = self.a.post("/api/v1/products/", {"sku": "N1", "name": "n", "category": str(cat_b.id),
                          "base_uom": str(self.prod_a.base_uom_id)}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_same_sku_allowed_in_different_tenants_but_not_twice_in_one(self):
        ok = self.a.post("/api/v1/products/", {"sku": "SKU-B", "name": "n", "base_uom": str(self.prod_a.base_uom_id)}, format="json")
        self.assertEqual(ok.status_code, 201)
        dup = self.a.post("/api/v1/products/", {"sku": "sku-b", "name": "n", "base_uom": str(self.prod_a.base_uom_id)}, format="json")
        self.assertEqual(dup.status_code, 400)

    def test_balances_movements_and_audit_are_scoped(self):
        self.assertEqual(self.a.get("/api/v1/balances/").data["count"], 0)
        self.assertEqual(self.a.get("/api/v1/movements/").data["count"], 0)
        events = self.a.get("/api/v1/audit-events/").data["results"]
        self.assertTrue(all(e["actor_email"] in ("", "a@a.test") for e in events))

    def test_client_cannot_override_organisation_on_create(self):
        res = self.a.post("/api/v1/products/", {"sku": "N2", "name": "n", "organisation": str(self.org_b.id),
                          "base_uom": str(self.prod_a.base_uom_id)}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Product.objects.get(sku="N2").organisation_id, self.org_a.id)
