import uuid

from django.db import models


class TenantModel(models.Model):
    """Base for every tenant-owned record: UUID pk (no enumerable ids) + organisation FK."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey("tenancy.Organisation", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class MutableTenantModel(TenantModel):
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
