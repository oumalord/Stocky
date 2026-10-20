import os

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Membership, Role, User
from apps.tenancy.models import Organisation
from apps.tenancy.services import create_organisation


class Command(BaseCommand):
    help = "Create an organisation administrator. The password is read from STOCKPILOT_ADMIN_PASSWORD."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--organisation", required=True, help="Existing organisation name, or a new one to create.")

    def handle(self, *args, email, organisation, **opts):
        password = os.environ.get("STOCKPILOT_ADMIN_PASSWORD", "")
        if not password:
            raise CommandError("Set STOCKPILOT_ADMIN_PASSWORD in the environment.")
        email = email.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("A user with this email already exists.")
        try:
            validate_password(password, user=User(email=email))
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages))
        with transaction.atomic():
            user = User.objects.create_user(email, password, full_name="Administrator")
            org = Organisation.objects.filter(name=organisation).first()
            if org is None:
                create_organisation(name=organisation, owner=user)
                role = "owner"
            else:
                Membership.objects.create(user=user, organisation=org, role=Role.objects.get(organisation=org, code="admin"))
                role = "admin"
        self.stdout.write(self.style.SUCCESS(f"Created {email} as {role} of '{organisation}'."))
