import threading
import unittest
from decimal import Decimal

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.core.errors import InsufficientStock
from apps.inventory.models import InventoryBalance, StockMovement
from apps.inventory.services.ledger import post_movement

from .helpers import main_location, make_org, make_product


@unittest.skipUnless(connection.vendor == "postgresql", "row-level locking needs PostgreSQL")
class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.org, self.owner = make_org()
        self.p = make_product(self.org)
        self.loc = main_location(self.org)

    def _run(self, fn, n):
        results, lock = [], threading.Lock()

        def worker(i):
            try:
                out = fn(i)
            except InsufficientStock:
                out = "insufficient"
            finally:
                connections.close_all()
            with lock:
                results.append(out)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        return results

    def test_parallel_sales_never_oversell(self):
        post_movement(org=self.org, product=self.p, location=self.loc, qty_delta=5, movement_type="RECEIPT", idempotency_key="seed")
        results = self._run(lambda i: post_movement(org=self.org, product=self.p, location=self.loc, qty_delta=-1,
                            movement_type="SALE", idempotency_key=f"s{i}")[1], 12)
        self.assertEqual(results.count(True), 5)
        self.assertEqual(results.count("insufficient"), 7)
        self.assertEqual(InventoryBalance.objects.get(product=self.p).on_hand, Decimal("0"))

    def test_parallel_duplicate_requests_post_once(self):
        results = self._run(lambda i: post_movement(org=self.org, product=self.p, location=self.loc, qty_delta=3,
                            movement_type="RECEIPT", idempotency_key="dup")[1], 8)
        self.assertEqual(results.count(True), 1)
        self.assertEqual(StockMovement.objects.filter(idempotency_key="dup").count(), 1)
        self.assertEqual(InventoryBalance.objects.get(product=self.p).on_hand, Decimal("3"))
