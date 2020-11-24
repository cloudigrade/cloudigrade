"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions, renderers, routers
from rest_framework.schemas import get_schema_view

from api import views as public_views
from api.internal import views as internal_views

router = routers.DefaultRouter()
router.register(r"accounts", public_views.AccountViewSet, basename="v2-account")
router.register(r"instances", public_views.InstanceViewSet, basename="v2-instance")
router.register(r"images", public_views.MachineImageViewSet, basename="v2-machineimage")
router.register(r"sysconfig", public_views.SysconfigViewSet, basename="v2-sysconfig")
router.register(
    r"concurrent", public_views.DailyConcurrentUsageViewSet, basename="v2-concurrent"
)

urlpatterns = [
    url(r"^api/cloudigrade/v2/", include(router.urls)),
    path(
        "api/cloudigrade/v2/openapi.json",
        get_schema_view(
            title="Cloudigrade",
            renderer_classes=[
                renderers.JSONOpenAPIRenderer,
            ],
            permission_classes=[permissions.AllowAny],
            authentication_classes=[],
            public=True,
        ),
        name="openapi-schema",
    ),
    url(r"^internal/api/cloudigrade/v1/", internal_views.availability_check),
    url(r"^internal/api-auth/", include("rest_framework.urls")),
    url(r"^internal/healthz/", include("health_check.urls")),
    path("internal/admin/", admin.site.urls),
    url(r"^internal/", include("django_prometheus.urls")),
]
