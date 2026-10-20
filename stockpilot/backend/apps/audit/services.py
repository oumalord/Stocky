from apps.core.context import get_correlation_id

from .models import AuditEvent


def record(*, organisation, actor=None, action, target_type="", target_id="", before=None, after=None):
    return AuditEvent.objects.create(
        organisation=organisation,
        actor_id=getattr(actor, "pk", None),
        actor_email=getattr(actor, "email", "") or "",
        action=action, target_type=target_type, target_id=target_id,
        before=before, after=after, correlation_id=get_correlation_id(),
    )
