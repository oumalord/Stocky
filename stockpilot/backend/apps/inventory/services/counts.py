from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.errors import IdempotencyConflict

from ..models import InventoryBalance, StockCount, StockCountEntry, StockCountLine, StockMovement

PERCENT_STEP = Decimal("0.0001")
QTY_STEP = Decimal("0.0001")


def create_stock_count(*, organisation, location, products, blind, idempotency_key, user):
    product_ids = [product.pk for product in products]
    try:
        with transaction.atomic():
            existing = StockCount.objects.select_for_update().filter(
                organisation=organisation, idempotency_key=idempotency_key).first()
            if existing:
                _validate_replay(existing, location, blind, product_ids)
                return existing, False

            for product in sorted(products, key=lambda item: str(item.pk)):
                InventoryBalance.objects.get_or_create(
                    organisation=organisation, location=location, product=product,
                    defaults={"on_hand": Decimal("0")})
            balances = InventoryBalance.objects.select_for_update().filter(
                organisation=organisation, location=location, product_id__in=product_ids).order_by("product_id")
            on_hand = {balance.product_id: balance.on_hand for balance in balances}
            snapshot_at = timezone.now()
            count = StockCount.objects.create(organisation=organisation, location=location, blind=blind,
                                              snapshot_at=snapshot_at, idempotency_key=idempotency_key, created_by=user)
            StockCountLine.objects.bulk_create([
                StockCountLine(
                    organisation=organisation,
                    count=count,
                    product=product,
                    expected_at_start=on_hand.get(product.pk, Decimal("0")),
                    unit_cost=product.standard_cost,
                    retail_price=product.selling_price,
                ) for product in products
            ])
    except IntegrityError:
        existing = StockCount.objects.filter(organisation=organisation, idempotency_key=idempotency_key).first()
        if existing is None:
            raise
        _validate_replay(existing, location, blind, product_ids)
        return existing, False
    return count, True


def _validate_replay(existing, location, blind, product_ids):
    existing_products = list(existing.lines.order_by("product_id").values_list("product_id", flat=True))
    if (existing.location_id != location.pk or existing.blind != blind
            or existing_products != sorted(product_ids, key=str)):
        raise ValidationError({"idempotency_key": "This key was already used for a different count."})


def record_counted_quantity(*, count, product, quantity, idempotency_key, user):
    with transaction.atomic():
        locked_count = StockCount.objects.select_for_update().get(pk=count.pk)
        if locked_count.status != "DRAFT":
            raise ValidationError("Only draft counts can be edited.")
        line = StockCountLine.objects.select_related("product__base_uom").filter(
            organisation=locked_count.organisation, count=locked_count, product=product).first()
        if line is None:
            raise ValidationError({"product": "This product is not part of the count."})
        if not line.product.base_uom.allows_fraction and quantity != quantity.to_integral_value():
            raise ValidationError({"counted_quantity": f"{line.product.base_uom.code} does not allow fractional quantities."})
        prior_entry = StockCountEntry.objects.select_for_update().filter(
            organisation=locked_count.organisation, idempotency_key=idempotency_key).first()
        if prior_entry:
            if prior_entry.line_id != line.pk or prior_entry.counted_quantity != quantity:
                raise IdempotencyConflict("This idempotency key was already used for a different count entry.")
            return line, False

        counted_at = timezone.now()
        try:
            with transaction.atomic():
                StockCountEntry.objects.create(
                    organisation=locked_count.organisation, line=line, counted_quantity=quantity,
                    counted_at=counted_at, counted_by=user, idempotency_key=idempotency_key)
        except IntegrityError:
            prior_entry = StockCountEntry.objects.filter(
                organisation=locked_count.organisation, idempotency_key=idempotency_key).first()
            if prior_entry is None or prior_entry.line_id != line.pk or prior_entry.counted_quantity != quantity:
                raise IdempotencyConflict("This idempotency key was already used for a different count entry.")
            return line, False

        line.counted_quantity = quantity
        line.counted_at = counted_at
        line.counted_by = user
        line.save(update_fields=["counted_quantity", "counted_at", "counted_by", "updated_at"])
    return line, True


def submit_stock_count(*, count):
    with transaction.atomic():
        locked_count = StockCount.objects.select_for_update().get(pk=count.pk)
        if locked_count.status == "SUBMITTED":
            return locked_count, False
        if locked_count.status != "DRAFT":
            raise ValidationError("Only draft counts can be submitted.")

        lines = list(StockCountLine.objects.select_for_update().select_related("product").filter(
            count=locked_count).order_by("product_id"))
        if not lines:
            raise ValidationError("A count must contain at least one product.")
        if any(line.counted_quantity is None or line.counted_at is None for line in lines):
            raise ValidationError("Enter a counted quantity for every product before submitting.")

        for line in lines:
            intervening = StockMovement.objects.filter(
                organisation=locked_count.organisation,
                location=locked_count.location,
                product=line.product,
                created_at__gt=locked_count.snapshot_at,
                created_at__lte=line.counted_at,
            ).aggregate(total=Sum("qty_delta"))["total"] or Decimal("0")
            expected = line.expected_at_start + intervening
            variance = line.counted_quantity - expected
            line.expected_quantity = expected
            line.variance_quantity = variance
            if expected:
                line.variance_percent = (variance / abs(expected) * 100).quantize(PERCENT_STEP)
            elif variance == 0:
                line.variance_percent = Decimal("0")
            else:
                line.variance_percent = None
            amount = abs(variance) * line.unit_cost
            retail = abs(variance) * line.retail_price
            line.shortage_cost = amount if variance < 0 else Decimal("0")
            line.surplus_cost = amount if variance > 0 else Decimal("0")
            line.net_cost_variance = variance * line.unit_cost
            line.shortage_retail = retail if variance < 0 else Decimal("0")
            line.surplus_retail = retail if variance > 0 else Decimal("0")
            line.save(update_fields=["expected_quantity", "variance_quantity", "variance_percent", "shortage_cost",
                                     "surplus_cost", "net_cost_variance", "shortage_retail", "surplus_retail", "updated_at"])

        locked_count.status = "SUBMITTED"
        locked_count.submitted_at = timezone.now()
        locked_count.save(update_fields=["status", "submitted_at", "updated_at"])
    return locked_count, True