from decimal import Decimal

from django.test import TestCase

from apps.core.errors import IdempotencyConflict, InsufficientStock, InvalidMovement
from apps.core.immutable import ImmutableRecordError
from apps.inventory.models import InventoryBalance, StockMovement
from apps.inventory.services.ledger import find_balance_mismatches, post_movement, reverse_movement

from .helpers import client_for, main_location, make_org, make_product, post_move


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org()
        self.p = make_product(self.org)
        self.loc = main_location(self.org)

    def post(self, qty, mtype="RECEIPT", key="k", **kw):
        return post_movement(org=self.org, product=self.p, location=self.loc, qty_delta=qty,
                             movement_type=mtype, idempotency_key=key, user=self.owner, **kw)

    def on_hand(self):
        return InventoryBalance.objects.get(product=self.p, location=self.loc).on_hand

    def test_receipt_then_sale_updates_balance(self):
        self.post(10, "RECEIPT", "a")
        self.post(-4, "SALE", "b")
        self.assertEqual(self.on_hand(), Decimal("6"))

    def test_cannot_go_negative(self):
        self.post(2, "RECEIPT", "a")
        with self.assertRaises(InsufficientStock):
            self.post(-3, "SALE", "b")
        self.assertEqual(self.on_hand(), Decimal("2"))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_replay_with_same_key_posts_once(self):
        m1, c1 = self.post(5, "RECEIPT", "same")
        m2, c2 = self.post(5, "RECEIPT", "same")
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(m1.pk, m2.pk)
        self.assertEqual(self.on_hand(), Decimal("5"))

    def test_same_key_different_payload_conflicts(self):
        self.post(5, "RECEIPT", "same")
        with self.assertRaises(IdempotencyConflict):
            self.post(6, "RECEIPT", "same")

    def test_sign_and_precision_rules(self):
        with self.assertRaises(InvalidMovement):
            self.post(-1, "RECEIPT", "a")
        with self.assertRaises(InvalidMovement):
            self.post(1, "SALE", "b")
        with self.assertRaises(InvalidMovement):
            self.post(0, "RECEIPT", "c")
        with self.assertRaises(InvalidMovement):
            self.post(Decimal("1.5"), "RECEIPT", "d")  # pcs does not allow fractions
        with self.assertRaises(InvalidMovement):
            self.post(Decimal("1.00001"), "RECEIPT", "e")

    def test_fractional_allowed_for_kg(self):
        kg = make_product(self.org, "KG-1", uom="kg")
        post_movement(org=self.org, product=kg, location=self.loc, qty_delta=Decimal("2.5"),
                      movement_type="RECEIPT", idempotency_key="kg")
        self.assertEqual(InventoryBalance.objects.get(product=kg).on_hand, Decimal("2.5"))

    def test_reversal_restores_balance_and_cannot_repeat(self):
        m, _ = self.post(10, "RECEIPT", "a")
        rev, _ = reverse_movement(movement=m, user=self.owner, reason="entered twice", idempotency_key="r1")
        self.assertEqual(self.on_hand(), Decimal("0"))
        self.assertEqual(rev.reverses_id, m.id)
        with self.assertRaises(InvalidMovement):
            reverse_movement(movement=m, user=self.owner, reason="again", idempotency_key="r2")
        with self.assertRaises(InvalidMovement):
            reverse_movement(movement=rev, user=self.owner, reason="reverse the reversal", idempotency_key="r3")

    def test_reversal_that_would_go_negative_is_blocked(self):
        m, _ = self.post(5, "RECEIPT", "a")
        self.post(-5, "SALE", "b")
        with self.assertRaises(InsufficientStock):
            reverse_movement(movement=m, user=self.owner, reason="oops", idempotency_key="r1")

    def test_ledger_rows_are_immutable(self):
        m, _ = self.post(5, "RECEIPT", "a")
        m.reason = "tampered"
        with self.assertRaises(ImmutableRecordError):
            m.save()
        with self.assertRaises(ImmutableRecordError):
            m.delete()
        with self.assertRaises(ImmutableRecordError):
            StockMovement.objects.filter(pk=m.pk).update(qty_delta=99)
        with self.assertRaises(ImmutableRecordError):
            StockMovement.objects.all().delete()

    def test_reconciliation_detects_tampered_cache(self):
        self.post(5, "RECEIPT", "a")
        self.assertEqual(find_balance_mismatches(self.org), [])
        InventoryBalance.objects.filter(product=self.p).update(on_hand=Decimal("99"))
        mismatches = find_balance_mismatches(self.org)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0]["ledger"], Decimal("5"))

    def test_sensitive_types_are_audited(self):
        from apps.audit.models import AuditEvent
        self.post(5, "RECEIPT", "a")
        self.post(-1, "WRITE_OFF", "b", reason="damaged in store")
        self.assertTrue(AuditEvent.objects.filter(action="stock.write_off").exists())


class LedgerApiTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org()
        self.p = make_product(self.org)
        self.loc = main_location(self.org)
        self.c = client_for(self.owner, self.org)

    def test_idempotency_key_is_required(self):
        res = self.c.post("/api/v1/movements/", {"product": str(self.p.id), "location": str(self.loc.id),
                          "qty_delta": "1", "movement_type": "RECEIPT"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["code"], "missing_idempotency_key")

    def test_post_replay_and_balance_via_api(self):
        first = post_move(self.c, self.p, self.loc, 7, "RECEIPT", "api-1")
        replay = post_move(self.c, self.p, self.loc, 7, "RECEIPT", "api-1")
        self.assertEqual((first.status_code, replay.status_code), (201, 200))
        self.assertEqual(first.data["id"], replay.data["id"])
        bal = self.c.get("/api/v1/balances/").data["results"][0]
        self.assertEqual(Decimal(bal["on_hand"]), Decimal("7"))

    def test_insufficient_stock_returns_409_with_error_shape(self):
        res = post_move(self.c, self.p, self.loc, -1, "SALE", "api-2")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(set(res.data), {"code", "message", "fields", "correlation_id"})

    def test_reverse_endpoint(self):
        m = post_move(self.c, self.p, self.loc, 4, "RECEIPT", "api-3").data
        res = self.c.post(f"/api/v1/movements/{m['id']}/reverse/", {"reason": "duplicate"}, format="json", HTTP_IDEMPOTENCY_KEY="api-3r")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Decimal(self.c.get("/api/v1/balances/").data["results"][0]["on_hand"]), 0)

    def test_there_is_no_update_or_delete_route_for_movements(self):
        m = post_move(self.c, self.p, self.loc, 4, "RECEIPT", "api-4").data
        self.assertEqual(self.c.delete(f"/api/v1/movements/{m['id']}/").status_code, 405)
        self.assertEqual(self.c.patch(f"/api/v1/movements/{m['id']}/", {"qty_delta": "1"}, format="json").status_code, 405)
