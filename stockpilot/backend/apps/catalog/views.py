from rest_framework import viewsets

from apps.core.viewsets import TenantViewSetMixin

from .models import Category, Product, UnitOfMeasure
from .serializers import CategorySerializer, ProductSerializer, UnitOfMeasureSerializer

_READ = {"list": "product.view", "retrieve": "product.view"}
_WRITE = {a: "product.manage" for a in ("create", "update", "partial_update", "destroy")}


class ProductViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    model = Product
    audit_prefix = "product"
    serializer_class = ProductSerializer
    permission_map = {**_READ, **_WRITE}
    search_fields = ["sku", "name", "barcode"]
    ordering_fields = ["sku", "name", "created_at"]
    ordering = ["sku"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("category", "base_uom")
        if self.action == "list" and self.request.query_params.get("archived") != "true":
            qs = qs.filter(is_archived=False)
        return qs

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=["is_archived", "updated_at"])
        self.audit("archived", instance)


class CategoryViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    model = Category
    audit_prefix = "category"
    serializer_class = CategorySerializer
    permission_map = {**_READ, **_WRITE}
    ordering = ["name"]
    http_method_names = ["get", "post", "patch", "head", "options"]


class UnitOfMeasureViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    model = UnitOfMeasure
    serializer_class = UnitOfMeasureSerializer
    permission_map = _READ
    ordering = ["code"]
