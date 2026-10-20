from django.test import TestCase

from apps.audit.models import AuditEvent
from apps.core.immutable import ImmutableRecordError

from .helpers import client_for, make_org, make_product


class AuditTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org()
        self.c = client_for(self.owner, self.org)

    def test_product_create_update_archive_are_audited_with_actor_and_correlation_id(self):
        uom = make_product(self.org, "TMP").base_uom_id
        res = self.c.post("/api/v1/products/", {"sku": "A1", "name": "n", "base_uom": str(uom)}, format="json", HTTP_X_REQUEST_ID="trace-123")
        pid = res.data["id"]
        self.c.patch(f"/api/v1/products/{pid}/", {"name": "renamed"}, format="json")
        self.c.delete(f"/api/v1/products/{pid}/")
        actions = list(AuditEvent.objects.filter(target_id=pid).order_by("created_at").values_list("action", flat=True))
        self.assertEqual(actions, ["product.created", "product.updated", "product.archived"])
        created = AuditEvent.objects.get(target_id=pid, action="product.created")
        self.assertEqual(created.actor_email, self.owner.email)
        self.assertEqual(created.correlation_id, "trace-123")
        updated = AuditEvent.objects.get(target_id=pid, action="product.updated")
        self.assertEqual((updated.before["name"], updated.after["name"]), ("n", "renamed"))

    def test_archived_products_are_hidden_from_default_list_but_kept(self):
        uom = make_product(self.org, "TMP").base_uom_id
        pid = self.c.post("/api/v1/products/", {"sku": "A2", "name": "n", "base_uom": str(uom)}, format="json").data["id"]
        self.c.delete(f"/api/v1/products/{pid}/")
        self.assertNotIn("A2", {r["sku"] for r in self.c.get("/api/v1/products/").data["results"]})
        self.assertIn("A2", {r["sku"] for r in self.c.get("/api/v1/products/?archived=true").data["results"]})

    def test_audit_events_cannot_be_changed_or_deleted(self):
        ev = AuditEvent.objects.filter(organisation=self.org).first()
        ev.action = "tampered"
        with self.assertRaises(ImmutableRecordError):
            ev.save()
        with self.assertRaises(ImmutableRecordError):
            ev.delete()
        with self.assertRaises(ImmutableRecordError):
            AuditEvent.objects.all().update(action="x")

    def test_no_write_routes_exist_for_audit(self):
        self.assertEqual(self.c.post("/api/v1/audit-events/", {}, format="json").status_code, 405)
