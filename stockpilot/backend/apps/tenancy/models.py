import uuid

from django.db import models

from apps.core.models import MutableTenantModel


class Organisation(models.Model):
    COSTING = [("WEIGHTED_AVERAGE", "Weighted average"), ("FIFO", "FIFO")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    currency = models.CharField(max_length=3, default="KES")
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    costing_method = models.CharField(max_length=20, choices=COSTING, default="WEIGHTED_AVERAGE")
    is_demo = models.BooleanField(default=False)  # demo data must always be labelled in UI and exports
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Branch(MutableTenantModel):
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organisation", "code"], name="uniq_branch_code_per_org")]
