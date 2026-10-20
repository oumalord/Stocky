from django.core.exceptions import ValidationError
from rest_framework.permissions import BasePermission


def resolve_membership(request):
    """The caller's active membership for the requested organisation, or None.

    Organisation comes from the X-Organisation-Id header; if omitted and the user belongs to
    exactly one organisation, that one is used. Membership is always verified server-side.
    """
    from apps.accounts.models import Membership

    qs = Membership.objects.select_related("organisation", "role").filter(
        user=request.user, is_active=True, organisation__is_active=True
    )
    org_id = request.headers.get("X-Organisation-Id")
    if org_id:
        try:
            return qs.filter(organisation_id=org_id).first()
        except (ValueError, TypeError, ValidationError):
            return None
    memberships = list(qs[:2])
    return memberships[0] if len(memberships) == 1 else None


class HasOrgPermission(BasePermission):
    """Deny-by-default: a view must map each action to a permission code in `permission_map`."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        membership = resolve_membership(request)
        if membership is None:
            return False
        request.membership = membership
        request.org = membership.organisation
        action = getattr(view, "action", None)
        if action is None:
            return True  # No router action exists for this verb; DRF returns 405 after permission checks.
        code = getattr(view, "permission_map", {}).get(action)
        return bool(code) and membership.has_perm(code)
