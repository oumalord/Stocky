import contextvars

_correlation_id = contextvars.ContextVar("correlation_id", default="")


def set_correlation_id(value):
    return _correlation_id.set(value)


def get_correlation_id():
    return _correlation_id.get()
