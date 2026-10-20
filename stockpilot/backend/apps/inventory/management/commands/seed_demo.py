from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Membership, Role, User
from apps.accounts.permissions_catalog import DEFAULT_ROLES
from apps.catalog.models import Category, Product, UnitOfMeasure
from apps.inventory.models import StockLocation
from apps.inventory.services.ledger import post_movement
from apps.tenancy.services import create_organisation

DEMO_PASSWORD = "demo-only-change-me-123"  # development only; command refuses to run when DEBUG is off


class Command(BaseCommand):
    help = "Create a clearly-labelled DEMO organisation with sample users, products and opening stock (dev only)."

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs with DJANGO_DEBUG=true.")
        if User.objects.filter(email="owner@demo.test").exists():
            raise CommandError("Demo data already exists.")
        owner = User.objects.create_user("owner@demo.test", DEMO_PASSWORD, full_name="Demo Owner")
        org = create_organisation(name="DEMO - Savanna Supermarket", owner=owner, is_demo=True)
        for code in DEFAULT_ROLES:
            if code in ("owner",):
                continue
            u = User.objects.create_user(f"{code}@demo.test", DEMO_PASSWORD, full_name=f"Demo {code.replace('_', ' ').title()}")
            Membership.objects.create(user=u, organisation=org, role=Role.objects.get(organisation=org, code=code))
        cat = Category.objects.create(organisation=org, name="Groceries")
        pcs, kg = (UnitOfMeasure.objects.get(organisation=org, code=c) for c in ("pcs", "kg"))
        loc = StockLocation.objects.get(organisation=org, code="MAIN-STORE")
        rows = [("MILK-500", "Fresh milk 500ml", pcs, "58", "70", 120), ("RICE-2KG", "Pishori rice 2kg", pcs, "420", "520", 60),
                ("SUGAR-1KG", "Sugar 1kg", pcs, "150", "185", 90), ("TOMATO", "Tomatoes (loose)", kg, "80", "120", 40)]
        for sku, name, uom, cost, price, qty in rows:
            p = Product.objects.create(organisation=org, sku=sku, name=name, category=cat, base_uom=uom,
                                       standard_cost=Decimal(cost), selling_price=Decimal(price), reorder_level=Decimal(10))
            post_movement(org=org, product=p, location=loc, qty_delta=Decimal(qty), movement_type="OPENING_BALANCE",
                          idempotency_key=f"seed-{sku}", user=owner, reason="DEMO opening balance", unit_cost=Decimal(cost))
        self.stdout.write(self.style.WARNING(f"DEMO org created. Log in as owner@demo.test / {DEMO_PASSWORD} (dev only)."))
