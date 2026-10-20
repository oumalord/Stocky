from rest_framework import serializers

from apps.catalog.models import Product
from apps.core.viewsets import OrgPKField
from apps.tenancy.models import Branch

from .models import InventoryBalance, StockCount, StockCountLine, StockLocation, StockMovement
from .services.ledger import API_POSTABLE


class StockLocationSerializer(serializers.ModelSerializer):
    branch = OrgPKField(queryset=Branch.objects.all(), required=False, allow_null=True)
    parent = OrgPKField(queryset=StockLocation.objects.all(), required=False, allow_null=True)

    class Meta:
        model = StockLocation
        fields = ["id", "code", "name", "kind", "branch", "parent", "is_active"]
        read_only_fields = ["id"]

    def validate_code(self, value):
        qs = StockLocation.objects.filter(organisation=self.context["request"].org, code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A location with this code already exists.")
        return value


class MovementSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)
    reversed = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_sku", "location", "location_code", "qty_delta", "movement_type",
                  "reference", "reason", "unit_cost", "source", "created_by_email", "occurred_at",
                  "created_at", "reverses", "reversed", "idempotency_key"]
        read_only_fields = fields

    def get_reversed(self, obj):
        return hasattr(obj, "reversed_by")


class MovementCreateSerializer(serializers.Serializer):
    product = OrgPKField(queryset=Product.objects.select_related("base_uom"))
    location = OrgPKField(queryset=StockLocation.objects.all())
    qty_delta = serializers.DecimalField(max_digits=18, decimal_places=4)
    movement_type = serializers.ChoiceField(choices=sorted(API_POSTABLE))
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, allow_null=True, min_value=0)
    occurred_at = serializers.DateTimeField(required=False)


class ReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class BalanceSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)

    class Meta:
        model = InventoryBalance
        fields = ["id", "product", "product_sku", "product_name", "location", "location_code", "on_hand", "updated_at"]
        read_only_fields = fields


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "code", "name", "is_active"]
        read_only_fields = fields


class StockCountCreateSerializer(serializers.Serializer):
    location = OrgPKField(queryset=StockLocation.objects.all())
    products = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    blind = serializers.BooleanField(default=False)

    def validate_products(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each product may appear only once in a count.")
        products = list(Product.objects.filter(organisation=self.context["request"].org,
                                               id__in=value, is_archived=False).select_related("base_uom"))
        if len(products) != len(value):
            raise serializers.ValidationError("One or more products are unavailable in this organisation.")
        by_id = {product.id: product for product in products}
        return [by_id[product_id] for product_id in value]


class StockCountEntrySerializer(serializers.Serializer):
    product = OrgPKField(queryset=Product.objects.all())
    counted_quantity = serializers.DecimalField(max_digits=18, decimal_places=4, min_value=0)


class StockCountLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    count_reference = serializers.CharField(source="count.reference", read_only=True)
    location_code = serializers.CharField(source="count.location.code", read_only=True)
    expected_at_start = serializers.SerializerMethodField()

    class Meta:
        model = StockCountLine
        fields = ["id", "count_reference", "location_code", "product", "product_sku", "product_name",
              "expected_at_start", "counted_quantity", "counted_at", "expected_quantity", "variance_quantity",
              "variance_percent", "unit_cost", "shortage_cost", "surplus_cost", "net_cost_variance",
              "shortage_retail", "surplus_retail"]
        read_only_fields = fields

    def get_expected_at_start(self, obj):
        if obj.count.blind and obj.count.status == "DRAFT":
            return None
        return obj.expected_at_start


class StockCountSerializer(serializers.ModelSerializer):
    location_code = serializers.CharField(source="location.code", read_only=True)
    created_by_email = serializers.CharField(source="created_by.email", read_only=True, default=None)
    lines = StockCountLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockCount
        fields = ["id", "reference", "location", "location_code", "status", "blind", "snapshot_at",
                  "submitted_at", "created_by_email", "created_at", "lines"]
        read_only_fields = fields
