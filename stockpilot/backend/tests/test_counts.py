from decimal import Decimal

from django.test import TestCase

from apps.core.immutable import ImmutableRecordError
from apps.inventory.models import StockCount, StockCountEntry

from .helpers import client_for, make_branch_location, make_org, make_product, make_user, main_location, post_move


class StockCountApiTests(TestCase):
    def setUp(self):
        self.org, self.owner = make_org()
        self.product = make_product(self.org)
        self.location = main_location(self.org)
        self.client = client_for(self.owner, self.org)

    def create_count(self, *, product=None, key="count-1", blind=False):
        product = product or self.product
        return self.client.post(
            "/api/v1/stock-counts/",
            {"location": str(self.location.pk), "products": [str(product.pk)], "blind": blind},
            format="json", HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_snapshot_reconciles_movements_through_count_time(self):
        post_move(self.client, self.product, self.location, 10, "RECEIPT", "receipt-1")
        created = self.create_count()
        self.assertEqual(created.status_code, 201)
        count_id = created.data["id"]

        post_move(self.client, self.product, self.location, -2, "SALE", "sale-1")
        recorded = self.client.post(
            f"/api/v1/stock-counts/{count_id}/record/",
            {"product": str(self.product.pk), "counted_quantity": "7"}, format="json",
            HTTP_IDEMPOTENCY_KEY="line-record-1",
        )
        self.assertEqual(recorded.status_code, 200)

        submitted = self.client.post(f"/api/v1/stock-counts/{count_id}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200)
        line = submitted.data["lines"][0]
        self.assertEqual(Decimal(line["expected_at_start"]), Decimal("10"))
        self.assertEqual(Decimal(line["expected_quantity"]), Decimal("8"))
        self.assertEqual(Decimal(line["variance_quantity"]), Decimal("-1"))
        self.assertEqual(Decimal(line["variance_percent"]), Decimal("-12.5"))
        self.assertEqual(Decimal(line["shortage_cost"]), Decimal("10"))
        self.assertEqual(Decimal(line["surplus_cost"]), Decimal("0"))
        self.assertEqual(Decimal(line["net_cost_variance"]), Decimal("-10"))

        variances = self.client.get("/api/v1/variances/")
        self.assertEqual(variances.status_code, 200)
        self.assertEqual(variances.data["count"], 1)

    def test_delayed_count_entry_replay_cannot_overwrite_a_later_entry(self):
        post_move(self.client, self.product, self.location, 10, "RECEIPT", "retry-receipt")
        count = self.create_count(key="retry-count")
        record_url = f"/api/v1/stock-counts/{count.data['id']}/record/"
        first_payload = {"product": str(self.product.pk), "counted_quantity": "10"}
        first = self.client.post(record_url, first_payload, format="json", HTTP_IDEMPOTENCY_KEY="first-entry")

        post_move(self.client, self.product, self.location, -2, "SALE", "after-count")
        second_payload = {"product": str(self.product.pk), "counted_quantity": "9"}
        second = self.client.post(record_url, second_payload, format="json", HTTP_IDEMPOTENCY_KEY="second-entry")
        conflict = self.client.post(
            record_url, {"product": str(self.product.pk), "counted_quantity": "11"},
            format="json", HTTP_IDEMPOTENCY_KEY="first-entry",
        )
        replay = self.client.post(record_url, first_payload, format="json", HTTP_IDEMPOTENCY_KEY="first-entry")
        submitted = self.client.post(f"/api/v1/stock-counts/{count.data['id']}/submit/", {}, format="json")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(replay.data["counted_quantity"], "9.0000")
        self.assertEqual(replay.data["counted_at"], second.data["counted_at"])
        self.assertEqual(Decimal(submitted.data["lines"][0]["expected_quantity"]), Decimal("8"))
        self.assertEqual(Decimal(submitted.data["lines"][0]["counted_quantity"]), Decimal("9"))
        entry = StockCountEntry.objects.get(idempotency_key="first-entry")
        entry.counted_quantity = Decimal("1")
        with self.assertRaises(ImmutableRecordError):
            entry.save()

    def test_unexpected_stock_has_undefined_percentage_and_gross_surplus_value(self):
        created = self.create_count()
        count_id = created.data["id"]
        self.client.post(
            f"/api/v1/stock-counts/{count_id}/record/",
            {"product": str(self.product.pk), "counted_quantity": "2"}, format="json",
            HTTP_IDEMPOTENCY_KEY="unexpected-stock-entry",
        )
        submitted = self.client.post(f"/api/v1/stock-counts/{count_id}/submit/", {}, format="json")
        line = submitted.data["lines"][0]
        self.assertIsNone(line["variance_percent"])
        self.assertEqual(Decimal(line["surplus_cost"]), Decimal("20"))
        self.assertEqual(Decimal(line["net_cost_variance"]), Decimal("20"))

    def test_blind_draft_hides_expected_quantity(self):
        post_move(self.client, self.product, self.location, 5, "RECEIPT", "receipt-blind")
        response = self.create_count(key="blind-count", blind=True)
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data["lines"][0]["expected_at_start"])

    def test_create_replay_is_idempotent_and_payload_conflicts_are_rejected(self):
        first = self.create_count()
        replay = self.create_count()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(first.data["id"], replay.data["id"])
        self.assertEqual(StockCount.objects.filter(organisation=self.org).count(), 1)

        other_product = make_product(self.org, sku="SKU-2")
        conflict = self.create_count(product=other_product)
        self.assertEqual(conflict.status_code, 400)

    def test_count_is_not_visible_to_another_tenant(self):
        created = self.create_count()
        other_org, other_owner = make_org(name="Other", email="owner@other.test")
        other_client = client_for(other_owner, other_org)

        self.assertEqual(other_client.get("/api/v1/stock-counts/").data["count"], 0)
        self.assertEqual(other_client.get(f"/api/v1/stock-counts/{created.data['id']}/").status_code, 404)

    def test_branch_limited_counter_only_sees_authorised_counts(self):
        allowed_branch, allowed_location = make_branch_location(self.org, "BR-1")
        visible = self.client.post(
            "/api/v1/stock-counts/",
            {"location": str(allowed_location.pk), "products": [str(self.product.pk)]},
            format="json", HTTP_IDEMPOTENCY_KEY="branch-visible",
        )
        hidden = self.create_count(key="branch-hidden")
        counter = make_user(self.org, "counter", "counter@acme.test", branches=(allowed_branch,))
        restricted = client_for(counter, self.org)

        self.assertEqual(visible.status_code, 201)
        self.assertEqual(restricted.get("/api/v1/stock-counts/").data["count"], 1)
        self.assertEqual(restricted.get(f"/api/v1/stock-counts/{hidden.data['id']}/").status_code, 404)
        self.assertEqual(restricted.get("/api/v1/variances/").status_code, 403)
        denied = restricted.post(
            "/api/v1/stock-counts/",
            {"location": str(self.location.pk), "products": [str(self.product.pk)]},
            format="json", HTTP_IDEMPOTENCY_KEY="branch-denied",
        )
        self.assertEqual(denied.status_code, 403)

    def test_submission_requires_all_lines_to_be_counted(self):
        response = self.create_count()
        count_id = response.data["id"]
        submitted = self.client.post(f"/api/v1/stock-counts/{count_id}/submit/", {}, format="json")

        self.assertEqual(submitted.status_code, 400)
        self.assertEqual(StockCount.objects.get(pk=count_id).status, "DRAFT")