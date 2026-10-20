from rest_framework import serializers

from apps.core.viewsets import OrgPKField

from .models import Category, Product, UnitOfMeasure


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        qs = Category.objects.filter(organisation=self.context["request"].org, name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "code", "name", "allows_fraction"]
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    category = OrgPKField(queryset=Category.objects.all(), required=False, allow_null=True)
    base_uom = OrgPKField(queryset=UnitOfMeasure.objects.all())

    class Meta:
        model = Product
        fields = ["id", "sku", "barcode", "name", "description", "category", "base_uom", "tracking",
                  "standard_cost", "selling_price", "reorder_level", "is_archived", "created_at", "updated_at"]
        read_only_fields = ["id", "is_archived", "created_at", "updated_at"]  # organisation is never client-settable

    def _unique(self, field, value):
        if not value:
            return value
        qs = Product.objects.filter(organisation=self.context["request"].org, **{f"{field}__iexact": value})
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f"A product with this {field} already exists.")
        return value

    def validate_sku(self, value):
        return self._unique("sku", value.strip())

    def validate_barcode(self, value):
        return self._unique("barcode", value.strip())
