"""API URL configuration for cloudigrade."""
from django.urls import include, path
from rest_framework import permissions, renderers, routers
from rest_framework.schemas import get_schema_view

from api import views

router = routers.DefaultRouter()
router.register("accounts", views.AccountViewSet, "v2-account")
router.register("instances", views.InstanceViewSet, "v2-instance")
router.register("images", views.MachineImageViewSet, "v2-machineimage")
router.register("sysconfig", views.SysconfigViewSet, "v2-sysconfig")
router.register("concurrent", views.DailyConcurrentUsageViewSet, "v2-concurrent")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "openapi.json",
        get_schema_view(
            title="Cloudigrade",
            renderer_classes=[renderers.JSONOpenAPIRenderer],
            permission_classes=[permissions.AllowAny],
            authentication_classes=[],
            public=True,
            urlconf="api.urls",
        ),
        name="openapi-schema",
    ),
]
