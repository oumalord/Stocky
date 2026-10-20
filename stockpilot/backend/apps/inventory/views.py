from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.services import record
from apps.core.errors import MissingIdempotencyKey
from apps.core.viewsets import TenantViewSetMixin, assert_location_allowed, scope_locations
from apps.tenancy.models import Branch

from .models import InventoryBalance, StockLocation, StockMovement
from .serializers import (BalanceSerializer, BranchSerializer, MovementCreateSerializer, MovementSerializer, ReverseSerializer,
                          StockCountCreateSerializer, StockCountEntrySerializer, StockCountLineSerializer,
                          StockCountSerializer, StockLocationSerializer)
from .services import ledger
from .services import counts
from .models import StockCount, StockCountLine


def _key(request):
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise MissingIdempotencyKey("Send an Idempotency-Key header (1-128 characters).")
    return key


class BranchViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    model = Branch
    permission_map = {"list": "location.view", "retrieve": "location.view"}
    ordering = ["code"]

    serializer_class = BranchSerializer


class StockLocationViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    model = StockLocation
    audit_prefix = "location"
    serializer_class = StockLocationSerializer
    permission_map = {"list": "location.view", "retrieve": "location.view", "create": "location.manage",
                      "update": "location.manage", "partial_update": "location.manage"}
    search_fields = ["code", "name"]
    ordering = ["code"]
    http_method_names = ["get", "post", "patch", "put", "head", "options"]

    def get_queryset(self):
        return scope_locations(super().get_queryset(), self.request)


class MovementViewSet(TenantViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Ledger. Rows are never edited or deleted; POST with an Idempotency-Key header."""

    model = StockMovement
    serializer_class = MovementSerializer
    permission_map = {"list": "movement.view", "retrieve": "movement.view",
                      "create": "movement.post", "reverse": "movement.reverse"}
    search_fields = ["reference", "product__sku", "product__name"]
    ordering_fields = ["occurred_at", "created_at"]

    def get_queryset(self):
        qs = scope_locations(super().get_queryset().select_related("product", "location", "created_by", "reversed_by"),
                             self.request, field="location__branch_id")
        p = self.request.query_params
        for param, field in (("product", "product_id"), ("location", "location_id"), ("movement_type", "movement_type")):
            if p.get(param):
                qs = qs.filter(**{field: p[param]})
        return qs

    def create(self, request, *args, **kwargs):
        key = _key(request)
        s = MovementCreateSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        d = s.validated_data
        assert_location_allowed(request, d["location"])
        movement, created = ledger.post_movement(
            org=request.org, product=d["product"], location=d["location"], qty_delta=d["qty_delta"],
            movement_type=d["movement_type"], idempotency_key=key, user=request.user, reference=d["reference"],
            reason=d["reason"], unit_cost=d.get("unit_cost"), occurred_at=d.get("occurred_at"))
        return Response(MovementSerializer(movement).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        movement = self.get_object()
        assert_location_allowed(request, movement.location)
        s = ReverseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reversal, created = ledger.reverse_movement(movement=movement, user=request.user,
                                                    reason=s.validated_data["reason"], idempotency_key=_key(request))
        return Response(MovementSerializer(reversal).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class BalanceViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    model = InventoryBalance
    serializer_class = BalanceSerializer
    permission_map = {"list": "movement.view", "retrieve": "movement.view"}
    search_fields = ["product__sku", "product__name"]
    ordering = ["product__sku"]

    def get_queryset(self):
        qs = scope_locations(super().get_queryset().select_related("product", "location"),
                             self.request, field="location__branch_id")
        for param, field in (("product", "product_id"), ("location", "location_id")):
            if self.request.query_params.get(param):
                qs = qs.filter(**{field: self.request.query_params[param]})
        return qs


class StockCountViewSet(TenantViewSetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                        mixins.CreateModelMixin, viewsets.GenericViewSet):
    model = StockCount
    serializer_class = StockCountSerializer
    permission_map = {"list": "count.view", "retrieve": "count.view", "create": "count.manage",
                      "record": "count.manage", "submit": "count.manage"}
    ordering = ["-created_at"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = scope_locations(super().get_queryset().select_related("location", "created_by").prefetch_related(
            "lines__product"), self.request, field="location__branch_id")
        status_filter = self.request.query_params.get("status")
        location_filter = self.request.query_params.get("location")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        if location_filter:
            qs = qs.filter(location_id=location_filter)
        return qs

    def create(self, request, *args, **kwargs):
        s = StockCountCreateSerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        location = s.validated_data["location"]
        assert_location_allowed(request, location)
        count, created = counts.create_stock_count(
            organisation=request.org, location=location, products=s.validated_data["products"],
            blind=s.validated_data["blind"], idempotency_key=_key(request), user=request.user)
        if created:
            record(organisation=request.org, actor=request.user, action="stock_count.created",
                   target_type="inventory.stockcount", target_id=str(count.pk),
                   after={"reference": count.reference, "location": str(location.pk), "blind": count.blind})
        return Response(StockCountSerializer(count, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def record(self, request, pk=None):
        count = self.get_object()
        s = StockCountEntrySerializer(data=request.data, context=self.get_serializer_context())
        s.is_valid(raise_exception=True)
        line, created = counts.record_counted_quantity(
            count=count, product=s.validated_data["product"], quantity=s.validated_data["counted_quantity"],
            idempotency_key=_key(request), user=request.user)
        if created:
            record(organisation=request.org, actor=request.user, action="stock_count.quantity_recorded",
                   target_type="inventory.stockcountline", target_id=str(line.pk),
                   after={"count": count.reference, "product": str(line.product_id),
                          "counted_quantity": str(line.counted_quantity)})
        return Response(StockCountLineSerializer(line, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        count = self.get_object()
        submitted, created = counts.submit_stock_count(count=count)
        if created:
            record(organisation=request.org, actor=request.user, action="stock_count.submitted",
                   target_type="inventory.stockcount", target_id=str(count.pk),
                   before={"status": "DRAFT"}, after={"status": "SUBMITTED"})
        submitted = self.get_queryset().get(pk=submitted.pk)
        return Response(StockCountSerializer(submitted, context=self.get_serializer_context()).data)


class VarianceViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    model = StockCountLine
    serializer_class = StockCountLineSerializer
    permission_map = {"list": "variance.view", "retrieve": "variance.view"}
    search_fields = ["product__sku", "product__name", "count__reference"]
    ordering_fields = ["counted_at", "variance_quantity", "shortage_cost", "surplus_cost"]
    ordering = ["-counted_at", "product__sku"]

    def get_queryset(self):
        qs = super().get_queryset().filter(count__status="SUBMITTED", variance_quantity__isnull=False).exclude(
            variance_quantity=0)
        qs = scope_locations(qs, self.request, field="count__location__branch_id")
        qs = qs.select_related("count", "count__location", "product")
        for param, field in (("product", "product_id"), ("location", "count__location_id")):
            if self.request.query_params.get(param):
                qs = qs.filter(**{field: self.request.query_params[param]})
        return qs
