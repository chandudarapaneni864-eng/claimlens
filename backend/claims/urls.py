from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnalyticsView, ApprovalQueueView, ClaimViewSet, DashboardView, DocumentViewSet, PaymentListView, RoutingRuleViewSet,
)

router = DefaultRouter()
router.register("claims", ClaimViewSet, basename="claim")
router.register("documents", DocumentViewSet, basename="document")
router.register("routing-rules", RoutingRuleViewSet, basename="routing-rule")

urlpatterns = [
    path("approvals/", ApprovalQueueView.as_view()),
    path("payments/", PaymentListView.as_view()),
    path("dashboard/", DashboardView.as_view()),
    path("analytics/", AnalyticsView.as_view()),
    path("", include(router.urls)),
]
