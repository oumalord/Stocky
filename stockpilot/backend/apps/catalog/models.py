from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import MutableTenantModel

MONEY = dict(max_digits=18, decimal_places=4, validators=[MinValueValidator(Decimal("0"))])


class Category(MutableTenantModel):
    name = models.CharField(max_length=120)

    class Meta:
        verbose_name_plural = "categories"
        constraints = [models.UniqueConstraint(fields=["organisation", "name"], name="uniq_category_per_org")]


class UnitOfMeasure(MutableTenantModel):
    code = models.CharField(max_length=12)
    name = models.CharField(max_length=60)
    allows_fraction = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organisation", "code"], name="uniq_uom_per_org")]


class Product(MutableTenantModel):
    TRACKING = [("NONE", "None"), ("BATCH", "Batch"), ("SERIAL", "Serial")]

    sku = models.CharField(max_length=64)
    barcode = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.PROTECT, related_name="products")
    base_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name="+")
    tracking = models.CharField(max_length=10, choices=TRACKING, default="NONE")
    standard_cost = models.DecimalField(default=Decimal("0"), **MONEY)   # cost basis, never retail value
    selling_price = models.DecimalField(default=Decimal("0"), **MONEY)   # retail value, kept separate
    reorder_level = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("0"),
                                        validators=[MinValueValidator(Decimal("0"))])
    is_archived = models.BooleanField(default=False)  # archive, never hard-delete

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organisation", "sku"], name="uniq_sku_per_org"),
            models.UniqueConstraint(fields=["organisation", "barcode"], condition=~models.Q(barcode=""),
                                    name="uniq_barcode_per_org"),
        ]
        indexes = [models.Index(fields=["organisation", "name"])]
