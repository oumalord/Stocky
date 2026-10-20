import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.immutable import ImmutableModel


class AuditEvent(ImmutableModel):
    """Append-only. Never store passwords, tokens or unnecessary personal data in before/after."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey("tenancy.Organisation", null=True, on_delete=models.PROTECT, related_name="+")
    actor_id = models.UUIDField(null=True, blank=True)
    actor_email = models.CharField(max_length=254, blank=True)  # snapshot so history survives user changes
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=80, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    correlation_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["organisation", "-created_at"])]
        ordering = ["-created_at"]
