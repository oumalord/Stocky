from decimal import Decimal

from rest_framework.test import APIClient

from apps.accounts.models import Membership, Role, User
from apps.catalog.models import Product, UnitOfMeasure
from apps.inventory.models import StockLocation
from apps.tenancy.models import Branch
from apps.tenancy.services import create_organisation

PW = "a-Strong-test-pw-123"


def make_org(name="Acme", email="owner@acme.test"):
    owner = User.objects.create_user(email, PW, full_name="Owner")
    return create_organisation(name=name, owner=owner), owner


def make_user(org, role_code, email, branches=()):
    user = User.objects.create_user(email, PW)
    m = Membership.objects.create(user=user, organisation=org, role=Role.objects.get(organisation=org, code=role_code))
    if branches:
        m.branches.set(branches)
    return user


def make_product(org, sku="SKU-1", uom="pcs", **kw):
    return Product.objects.create(organisation=org, sku=sku, name=f"Product {sku}",
                                  base_uom=UnitOfMeasure.objects.get(organisation=org, code=uom),
                                  standard_cost=Decimal("10"), **kw)


def main_location(org):
    return StockLocation.objects.get(organisation=org, code="MAIN-STORE")


def make_branch_location(org, code):
    branch = Branch.objects.create(organisation=org, code=code, name=code)
    return branch, StockLocation.objects.create(organisation=org, branch=branch, code=f"{code}-LOC", name=code)


def client_for(user, org=None):
    c = APIClient()
    c.force_authenticate(user)
    if org:
        c.credentials(HTTP_X_ORGANISATION_ID=str(org.id))
    return c


def post_move(client, product, location, qty, mtype, key, **extra):
    return client.post("/api/v1/movements/", {"product": str(product.id), "location": str(location.id),
                       "qty_delta": str(qty), "movement_type": mtype, **extra},
                       format="json", HTTP_IDEMPOTENCY_KEY=key)
