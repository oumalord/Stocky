import secrets

from django.db import transaction
from django.utils.text import slugify

from apps.audit.services import record

from .models import Branch, Organisation


def _unique_slug(name):
    base = slugify(name)[:60] or "org"
    slug = base
    while Organisation.objects.filter(slug=slug).exists():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


@transaction.atomic
def create_organisation(*, name, owner, currency="KES", timezone="Africa/Nairobi", is_demo=False):
    """Provision an organisation with default roles, a main branch/location and units of measure."""
    from apps.accounts.models import Membership, Role
    from apps.accounts.permissions_catalog import DEFAULT_ROLES
    from apps.catalog.models import UnitOfMeasure
    from apps.inventory.models import StockLocation

    org = Organisation.objects.create(name=name, slug=_unique_slug(name), currency=currency,
                                      timezone=timezone, is_demo=is_demo)
    roles = {code: Role.objects.create(organisation=org, code=code, name=spec["name"],
                                       permissions=spec["permissions"], is_system=True)
             for code, spec in DEFAULT_ROLES.items()}
    Membership.objects.create(user=owner, organisation=org, role=roles["owner"])
    branch = Branch.objects.create(organisation=org, code="MAIN", name="Main branch")
    StockLocation.objects.create(organisation=org, branch=branch, code="MAIN-STORE", name="Main store", kind="STORE")
    for code, uom_name, frac in [("pcs", "Pieces", False), ("kg", "Kilograms", True), ("l", "Litres", True)]:
        UnitOfMeasure.objects.create(organisation=org, code=code, name=uom_name, allows_fraction=frac)
    record(organisation=org, actor=owner, action="organisation.created", target_type="tenancy.organisation",
           target_id=str(org.pk), after={"name": name, "currency": currency, "is_demo": is_demo})
    return org
