"""API URL configuration for cloudigrade."""
from django.urls import include, path
from rest_framework import permissions, renderers, routers
from rest_framework.schemas import get_schema_view

from api import viewsets

# Prepare a list of DRF ViewSet routes.
routes = [
    ("accounts", viewsets.AccountViewSet, "account"),
    ("sysconfig", viewsets.SysconfigViewSet, "sysconfig"),
    ("azure-offer-template", viewsets.AzureOfferTemplateViewSet, "azure-offer"),
]

# Register all the DRF ViewSet routes with a common "v2-" basename prefix.
router = routers.DefaultRouter()
for (prefix, viewset, basename) in routes:
    basename = f"v2-{basename}"
    router.register(prefix, viewset, basename)

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
