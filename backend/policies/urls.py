from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PolicyViewSet

router = DefaultRouter()
router.register("policies", PolicyViewSet, basename="policy")

urlpatterns = [path("", include(router.urls))]
