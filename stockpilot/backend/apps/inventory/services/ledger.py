"""The only code allowed to change stock balances.

post_movement() runs in one transaction: lock the balance row -> check idempotency -> validate
-> insert ledger row -> update cached balance. Concurrent requests for the same product/location
serialise on the row lock, so stock cannot go negative or be double-posted.
"""
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services import record
from apps.core.errors import IdempotencyConflict, InsufficientStock, InvalidMovement

from ..models import InventoryBalance, StockMovement

QTY_STEP = Decimal("0.0001")
POSITIVE = {"OPENING_BALANCE", "RECEIPT", "SALES_RETURN", "TRANSFER_IN", "PRODUCTION_OUTPUT"}
NEGATIVE = {"SALE", "SUPPLIER_RETURN", "TRANSFER_OUT", "PRODUCTION_CONSUMPTION", "DAMAGE", "EXPIRY", "WRITE_OFF"}
EITHER = {"CORRECTION", "ADJUSTMENT", "REVERSAL"}
# Not postable through the public API: adjustments need an approved request (Slice C); reversals have their own endpoint.
API_POSTABLE = POSITIVE | NEGATIVE
AUDITED_TYPES = {"WRITE_OFF", "CORRECTION", "ADJUSTMENT", "REVERSAL"}


def _validate(org, product, location, qty_delta, movement_type):
    if product.organisation_id != org.id or location.organisation_id != org.id:
        raise InvalidMovement("Product or location does not belong to this organisation.")
    if product.is_archived:
        raise InvalidMovement("Archived products cannot be moved.")
    if not location.is_active:
        raise InvalidMovement("Location is inactive.")
    qty = Decimal(qty_delta)
    if qty == 0:
        raise InvalidMovement("Quantity must not be zero.")
    if qty != qty.quantize(QTY_STEP):
        raise InvalidMovement("Quantity supports at most 4 decimal places.")
    if not product.base_uom.allows_fraction and qty != qty.to_integral_value():
        raise InvalidMovement(f"{product.base_uom.code} does not allow fractional quantities.")
    if movement_type in POSITIVE and qty < 0:
        raise InvalidMovement(f"{movement_type} must have a positive quantity.")
    if movement_type in NEGATIVE and qty > 0:
        raise InvalidMovement(f"{movement_type} must have a negative quantity.")
    if movement_type not in POSITIVE | NEGATIVE | EITHER:
        raise InvalidMovement("Unknown movement type.")
    return qty


def _lock_balance(org, product, location):
    InventoryBalance.objects.get_or_create(organisation=org, product=product, location=location,
                                           defaults={"on_hand": Decimal("0")})
    return InventoryBalance.objects.select_for_update().get(organisation=org, product=product, location=location)


def _same_request(m, product, location, qty, movement_type, reference):
    return (m.product_id == product.id and m.location_id == location.id and m.qty_delta == qty
            and m.movement_type == movement_type and m.reference == reference)


def post_movement(*, org, product, location, qty_delta, movement_type, idempotency_key, user=None,
                  source="user", reference="", reason="", unit_cost=None, occurred_at=None, reverses=None):
    """Returns (movement, created). Replaying the same key with the same payload returns the original."""
    if not idempotency_key:
        raise InvalidMovement("An idempotency key is required.")
    qty = _validate(org, product, location, qty_delta, movement_type)
    with transaction.atomic():
        balance = _lock_balance(org, product, location)
        existing = StockMovement.objects.filter(organisation=org, idempotency_key=idempotency_key).first()
        if existing:
            if not _same_request(existing, product, location, qty, movement_type, reference):
                raise IdempotencyConflict("This idempotency key was already used for a different request.")
            return existing, False
        if reverses is not None and StockMovement.objects.filter(reverses=reverses).exists():
            raise InvalidMovement("This movement has already been reversed.")
        new_on_hand = balance.on_hand + qty
        if new_on_hand < 0:
            raise InsufficientStock(f"Only {balance.on_hand} on hand; cannot post {qty}.")
        try:
            with transaction.atomic():
                movement = StockMovement.objects.create(
                    organisation=org, product=product, location=location, qty_delta=qty,
                    movement_type=movement_type, reference=reference, reason=reason, source=source,
                    created_by=user, unit_cost=unit_cost, occurred_at=occurred_at or timezone.now(),
                    idempotency_key=idempotency_key, reverses=reverses)
        except IntegrityError:
            raise InvalidMovement("Conflicting movement; please retry.")
        balance.on_hand = new_on_hand
        balance.last_movement = movement
        balance.save(update_fields=["on_hand", "last_movement", "updated_at"])
        if movement_type in AUDITED_TYPES:
            record(organisation=org, actor=user, action=f"stock.{movement_type.lower()}",
                   target_type="inventory.stockmovement", target_id=str(movement.pk),
                   before={"on_hand": str(balance.on_hand - qty)}, after={"on_hand": str(new_on_hand), "reason": reason})
    return movement, True


def reverse_movement(*, movement, user, reason, idempotency_key):
    """Compensating entry: an equal and opposite movement linked to the original."""
    if movement.reverses_id:
        raise InvalidMovement("A reversal cannot itself be reversed.")
    return post_movement(
        org=movement.organisation, product=movement.product, location=movement.location,
        qty_delta=-movement.qty_delta, movement_type="REVERSAL", idempotency_key=idempotency_key,
        user=user, reference=f"REV:{movement.pk}", reason=reason, unit_cost=movement.unit_cost, reverses=movement)


def find_balance_mismatches(organisation=None):
    """Compare cached balances with the ledger sum. Any result indicates a bug or tampering."""
    ledger_qs = StockMovement.objects.all()
    bal_qs = InventoryBalance.objects.all()
    if organisation is not None:
        ledger_qs, bal_qs = ledger_qs.filter(organisation=organisation), bal_qs.filter(organisation=organisation)
    ledger = {(r["organisation_id"], r["product_id"], r["location_id"]): r["t"]
              for r in ledger_qs.values("organisation_id", "product_id", "location_id").annotate(t=Sum("qty_delta"))}
    out = []
    for b in bal_qs:
        key = (b.organisation_id, b.product_id, b.location_id)
        expected = ledger.pop(key, Decimal("0"))
        if expected != b.on_hand:
            out.append({"product": str(b.product_id), "location": str(b.location_id),
                        "cached": b.on_hand, "ledger": expected})
    out += [{"product": str(k[1]), "location": str(k[2]), "cached": None, "ledger": v} for k, v in ledger.items() if v != 0]
    return out
