from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.accounts import views as auth
from apps.audit.views import AuditEventViewSet
from apps.catalog.views import CategoryViewSet, ProductViewSet, UnitOfMeasureViewSet
from apps.inventory.views import (BalanceViewSet, BranchViewSet, MovementViewSet, StockCountViewSet,
                                  StockLocationViewSet, VarianceViewSet)

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("categories", CategoryViewSet, basename="category")
router.register("units", UnitOfMeasureViewSet, basename="unit")
router.register("branches", BranchViewSet, basename="branch")
router.register("locations", StockLocationViewSet, basename="location")
router.register("movements", MovementViewSet, basename="movement")
router.register("balances", BalanceViewSet, basename="balance")
router.register("stock-counts", StockCountViewSet, basename="stock-count")
router.register("variances", VarianceViewSet, basename="variance")
router.register("audit-events", AuditEventViewSet, basename="audit-event")

urlpatterns = [
    path("auth/csrf/", auth.CsrfView.as_view()),
    path("auth/register/", auth.RegisterView.as_view()),
    path("auth/login/", auth.LoginView.as_view()),
    path("auth/logout/", auth.LogoutView.as_view()),
    path("auth/me/", auth.MeView.as_view()),
] + router.urls
