import logging

from celery import shared_task

from .services.ledger import find_balance_mismatches

log = logging.getLogger(__name__)


@shared_task
def reconcile_balances():
    """Nightly: verify cached balances equal the ledger. Alerting hooks arrive with the alerts module."""
    mismatches = find_balance_mismatches()
    if mismatches:
        log.error("Balance/ledger mismatch on %d rows", len(mismatches))
    return len(mismatches)
