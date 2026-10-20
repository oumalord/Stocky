from django.db import models


class ImmutableRecordError(Exception):
    """Raised on any attempt to modify or delete an append-only record."""


class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ImmutableRecordError("Append-only records cannot be updated.")

    def bulk_update(self, *args, **kwargs):
        raise ImmutableRecordError("Append-only records cannot be updated.")

    def delete(self):
        raise ImmutableRecordError("Append-only records cannot be deleted.")


class ImmutableModel(models.Model):
    """Rows may be inserted once and never changed. A DB trigger (see audit.apps) backs this up on PostgreSQL."""

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableRecordError(f"{type(self).__name__} is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError(f"{type(self).__name__} is append-only.")
