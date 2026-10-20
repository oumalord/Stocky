import re
import uuid

from .context import _correlation_id

_SAFE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class CorrelationIdMiddleware:
    """Attach a correlation ID to every request, audit event and response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cid = request.headers.get("X-Request-ID", "")
        if not _SAFE.match(cid):
            cid = uuid.uuid4().hex
        request.correlation_id = cid
        token = _correlation_id.set(cid)
        try:
            response = self.get_response(request)
        finally:
            _correlation_id.reset(token)
        response["X-Request-ID"] = cid
        return response
