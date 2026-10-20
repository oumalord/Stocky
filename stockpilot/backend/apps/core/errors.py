from django.db import IntegrityError
from rest_framework import exceptions as drf_exc
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler

from .context import get_correlation_id


class DomainError(Exception):
    status_code = 400
    code = "domain_error"

    def __init__(self, message=""):
        super().__init__(message or self.code)


class InvalidMovement(DomainError):
    code = "invalid_movement"


class MissingIdempotencyKey(DomainError):
    code = "missing_idempotency_key"


class InsufficientStock(DomainError):
    status_code = 409
    code = "insufficient_stock"


class IdempotencyConflict(DomainError):
    status_code = 409
    code = "idempotency_conflict"


def _body(code, message, fields=None):
    return {"code": code, "message": message, "fields": fields or {}, "correlation_id": get_correlation_id()}


def api_exception_handler(exc, context):
    """One error shape for the whole API: {code, message, fields, correlation_id}."""
    if isinstance(exc, DomainError):
        return Response(_body(exc.code, str(exc)), status=exc.status_code)
    if isinstance(exc, IntegrityError):
        return Response(_body("conflict", "The request conflicts with existing data."), status=409)
    response = drf_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, drf_exc.ValidationError):
        response.data = _body("validation_error", "Validation failed.", {"errors": response.data})
    else:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        code = getattr(detail, "code", None) or "error"
        response.data = _body(str(code), str(detail or "Request failed."))
    return response
