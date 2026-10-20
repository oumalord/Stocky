import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.immutable import ImmutableModel
from apps.core.models import MutableTenantModel, TenantModel


class StockLocation(MutableTenantModel):
    KINDS = [("WAREHOUSE", "Warehouse"), ("STORE", "Store"), ("SHELF", "Shelf"), ("BIN", "Bin"),
             ("TRANSIT", "In transit"), ("QUARANTINE", "Quarantine")]

    branch = models.ForeignKey("tenancy.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="locations")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=12, choices=KINDS, default="STORE")
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organisation", "code"], name="uniq_location_code_per_org")]


class StockMovement(ImmutableModel, TenantModel):
    """Append-only ledger row. Corrections are new rows (REVERSAL), never edits."""

    TYPES = [(t, t.replace("_", " ").title()) for t in (
        "OPENING_BALANCE", "RECEIPT", "SALE", "SALES_RETURN", "SUPPLIER_RETURN", "TRANSFER_OUT", "TRANSFER_IN",
        "PRODUCTION_CONSUMPTION", "PRODUCTION_OUTPUT", "DAMAGE", "EXPIRY", "WRITE_OFF",
        "CORRECTION", "ADJUSTMENT", "REVERSAL")]

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="+")
    qty_delta = models.DecimalField(max_digits=18, decimal_places=4)
    movement_type = models.CharField(max_length=24, choices=TYPES)
    reference = models.CharField(max_length=80, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    source = models.CharField(max_length=20, default="user")  # user | integration | system
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    occurred_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=128)
    reverses = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by")

    class Meta:
        ordering = ["-occurred_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organisation", "idempotency_key"], name="uniq_idempotency_per_org"),
            models.CheckConstraint(condition=~Q(qty_delta=0), name="movement_qty_nonzero"),
        ]
        indexes = [models.Index(fields=["organisation", "product", "location", "-occurred_at"])]


class InventoryBalance(MutableTenantModel):
    """Cached projection of the ledger. Written only by ledger.post_movement; verified nightly."""

    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="+")
    on_hand = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    last_movement = models.ForeignKey(StockMovement, null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation", "product", "location"], name="uniq_balance_row"),
            models.CheckConstraint(condition=Q(on_hand__gte=0), name="balance_non_negative"),
        ]


def _count_reference():
    return f"SC-{uuid.uuid4().hex[:12].upper()}"


class StockCount(MutableTenantModel):
    STATUSES = [("DRAFT", "Draft"), ("SUBMITTED", "Submitted"), ("CANCELLED", "Cancelled")]

    reference = models.CharField(max_length=15, default=_count_reference)
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name="stock_counts")
    status = models.CharField(max_length=12, choices=STATUSES, default="DRAFT")
    blind = models.BooleanField(default=False)
    snapshot_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=128)
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation", "reference"], name="uniq_count_reference_per_org"),
            models.UniqueConstraint(fields=["organisation", "idempotency_key"], name="uniq_count_idempotency_per_org"),
        ]
        indexes = [models.Index(fields=["organisation", "status", "created_at"])]


class StockCountLine(MutableTenantModel):
    count = models.ForeignKey(StockCount, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="stock_count_lines")
    expected_at_start = models.DecimalField(max_digits=18, decimal_places=4)
    counted_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    counted_at = models.DateTimeField(null=True, blank=True)
    counted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    retail_price = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"))
    expected_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    variance_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    variance_percent = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    shortage_cost = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    surplus_cost = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    net_cost_variance = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    shortage_retail = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    surplus_retail = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["count", "product"], name="uniq_product_per_stock_count"),
            models.CheckConstraint(condition=Q(expected_at_start__gte=0), name="count_snapshot_nonnegative"),
            models.CheckConstraint(condition=Q(counted_quantity__isnull=True) | Q(counted_quantity__gte=0),
                                   name="counted_qty_nonnegative"),
        ]
        indexes = [models.Index(fields=["organisation", "product", "counted_at"])]


class StockCountEntry(ImmutableModel, TenantModel):
    line = models.ForeignKey(StockCountLine, on_delete=models.PROTECT, related_name="entries")
    counted_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    counted_at = models.DateTimeField()
    counted_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="+")
    idempotency_key = models.CharField(max_length=128)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation", "idempotency_key"],
                                    name="uniq_count_entry_idempotency_per_org"),
        ]
        indexes = [models.Index(fields=["organisation", "line", "counted_at"])]
