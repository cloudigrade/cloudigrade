"""Cloudigrade URL Configuration."""
from django.conf.urls import url
from django.contrib import admin
from django.urls import include, path
from rest_framework import renderers, routers
from rest_framework.schemas import get_schema_view

from api import views

router = routers.DefaultRouter()
router.register(r"accounts", views.AccountViewSet, basename="v2-account")
router.register(r"instances", views.InstanceViewSet, basename="v2-instance")
router.register(r"images", views.MachineImageViewSet, basename="v2-machineimage")
router.register(r"sysconfig", views.SysconfigViewSet, basename="v2-sysconfig")
router.register(
    r"concurrent", views.DailyConcurrentUsageViewSet, basename="v2-concurrent"
)

urlpatterns = [
    url(r"^v2/", include(router.urls)),
    url(r"^api-auth/", include("rest_framework.urls")),
    url(r"^healthz/", include("health_check.urls")),
    path(
        "v2/openapi.json",
        get_schema_view(
            title="Cloudigrade", renderer_classes=[renderers.JSONOpenAPIRenderer,],
        ),
        name="openapi-schema",
    ),
    path("admin/", admin.site.urls),
]
