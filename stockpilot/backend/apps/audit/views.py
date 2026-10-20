from rest_framework import serializers, viewsets

from apps.core.viewsets import TenantViewSetMixin

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = ["id", "actor_email", "action", "target_type", "target_id", "before", "after",
                  "correlation_id", "created_at"]
        read_only_fields = fields


class AuditEventViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only by construction: there is no write route and the model refuses writes."""

    model = AuditEvent
    serializer_class = AuditEventSerializer
    permission_map = {"list": "audit.view", "retrieve": "audit.view"}
    search_fields = ["action", "actor_email", "target_id"]

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ("action", "target_type"):
            if self.request.query_params.get(param):
                qs = qs.filter(**{param: self.request.query_params[param]})
        return qs
