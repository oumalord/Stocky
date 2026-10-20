import hashlib

from django.contrib.auth import authenticate, login, logout
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record
from apps.core.context import get_correlation_id
from apps.tenancy.services import create_organisation

from .models import User
from .serializers import LoginSerializer, RegisterSerializer


def me_payload(user):
    memberships = user.memberships.select_related("organisation", "role").filter(
        is_active=True, organisation__is_active=True)
    return {"id": str(user.pk), "email": user.email, "full_name": user.full_name, "memberships": [{
        "organisation_id": str(m.organisation_id), "organisation_name": m.organisation.name,
        "is_demo": m.organisation.is_demo, "currency": m.organisation.currency,
        "role": m.role.code, "permissions": m.role.permissions,
        "branch_ids": [str(b) for b in m.allowed_branch_ids()] if m.allowed_branch_ids() else None,
    } for m in memberships]}


class CsrfView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"detail": "ok"})


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        with transaction.atomic():
            user = User.objects.create_user(d["email"], d["password"], full_name=d["full_name"])
            create_organisation(name=d["organisation_name"], owner=user, currency=d["currency"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(me_payload(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        email = s.validated_data["email"].strip().lower()
        user = authenticate(request, username=email, password=s.validated_data["password"])
        if user is None or not user.is_active:
            digest = hashlib.sha256(email.encode()).hexdigest()[:12]  # no raw email in the log
            record(organisation=None, action="auth.login_failed", target_type="auth", target_id=digest)
            return Response({"code": "invalid_credentials", "message": "Invalid email or password.",
                             "fields": {}, "correlation_id": get_correlation_id()}, status=401)
        login(request, user)
        first = user.memberships.filter(is_active=True).select_related("organisation").first()
        record(organisation=first.organisation if first else None, actor=user, action="auth.login")
        return Response(me_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(me_payload(request.user))
