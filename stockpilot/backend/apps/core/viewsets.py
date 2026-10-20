from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.audit.services import record


class OrgPKField(serializers.PrimaryKeyRelatedField):
    """Related-object field that can only see rows of the caller's organisation (prevents cross-tenant references)."""

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.context.get("request")
        org = getattr(request, "org", None)
        return qs.none() if org is None else qs.filter(organisation=org)


class TenantViewSetMixin:
    """Scopes every queryset to request.org and audits create/update. Set `model` and `audit_prefix`."""

    model = None
    audit_prefix = ""

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.model.objects.none()
        return self.model.objects.filter(organisation=self.request.org)

    def audit(self, action, instance, before=None, after=None):
        record(organisation=self.request.org, actor=self.request.user, action=f"{self.audit_prefix}.{action}",
               target_type=instance._meta.label_lower, target_id=str(instance.pk), before=before, after=after)

    def perform_create(self, serializer):
        instance = serializer.save(organisation=self.request.org)
        self.audit("created", instance, after=dict(serializer.data))

    def perform_update(self, serializer):
        before = dict(self.get_serializer(serializer.instance).data)
        instance = serializer.save()
        self.audit("updated", instance, before=before, after=dict(serializer.data))


def allowed_branch_ids(request):
    """None = all branches; otherwise a set of branch ids the member is limited to."""
    return request.membership.allowed_branch_ids()


def scope_locations(qs, request, field="branch_id"):
    ids = allowed_branch_ids(request)
    return qs if ids is None else qs.filter(**{f"{field}__in": ids})


def assert_location_allowed(request, location):
    ids = allowed_branch_ids(request)
    if ids is not None and location.branch_id not in ids:
        raise PermissionDenied("You do not have access to this branch.")
