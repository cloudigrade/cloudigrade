"""Internal API URL configuration for cloudigrade."""
from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions, renderers, routers
from rest_framework.schemas import get_schema_view

from internal import views

# Prepare a list of DRF ViewSet routes.
routes = []

# URLs for slightly different internal versions of public viewset routes.
routes += [
    ("accounts", views.InternalAccountViewSet, "account"),
    ("concurrent", views.InternalDailyConcurrentUsageViewSet, "concurrent"),
]

# URLs for common models
# "None" for the third tuple value means to use the model's name.
routes += [
    ("users", views.InternalUserViewSet, "user"),
    ("periodictasks", views.InternalPeriodicTaskViewSet, None),
    ("usertasklocks", views.InternalUserTaskLockViewSet, None),
    ("cloudaccounts", views.InternalCloudAccountViewSet, None),
    ("instances", views.InternalInstanceViewSet, None),
    ("instanceevents", views.InternalInstanceEventViewSet, None),
    ("machineimages", views.InternalMachineImageViewSet, None),
    (r"runs", views.InternalRunViewSet, None),
    (
        "machineimageinspectionstarts",
        views.InternalMachineImageInspectionStartViewSet,
        None,
    ),
    ("concurrentusages", views.InternalConcurrentUsageViewSet, None),
    ("instancedefinitions", views.InternalInstanceDefinitionViewSet, None),
]

# URLs for AWS models
routes += [
    ("awscloudaccounts", views.InternalAwsCloudAccountViewSet, None),
    ("awsinstances", views.InternalAwsInstanceViewSet, None),
    ("awsmachineimages", views.InternalAwsMachineImageViewSet, None),
    ("awsmachineimagecopies", views.InternalAwsMachineImageCopyViewSet, None),
    ("awsinstanceevents", views.InternalAwsInstanceEventViewSet, None),
]

# URLs for Azure models
routes += [
    ("azurecloudaccounts", views.InternalAzureCloudAccountViewSet, None),
    ("azureinstances", views.InternalAzureInstanceViewSet, None),
    ("azuremachineimages", views.InternalAzureMachineImageViewSet, None),
    ("azureinstanceevents", views.InternalAzureInstanceEventViewSet, None),
]


class PermissiveAPIRootView(routers.APIRootView):
    """
    Override default permissions of APIRootView.

    Because DefaultRouter does not provide functionality to pass arguments to define the
    authentication and permission classes for its APIRootView, and our current Django
    configs for cloudigrade have restrictive defaults for authentication and permission,
    we have to force more relaxed settings into a custom class here to allow requests
    to the internal API to access the root view without authentication.
    """

    authentication_classes = []
    permission_classes = [permissions.AllowAny]


router = routers.DefaultRouter()
router.APIRootView = PermissiveAPIRootView

# Register all the DRF ViewSet routes with a common "internal-" basename prefix.
for (prefix, viewset, basename) in routes:
    if not basename:
        basename = router.get_default_basename(viewset)
    basename = f"internal-{basename}"
    router.register(prefix, viewset, basename=basename)

# Prepare a list of Django URL patterns.
urlpatterns = []

# URL Patterns for various automated service checks and metrics.
urlpatterns += [
    path("healthz/", include("health_check.urls")),
    path("", include("django_prometheus.urls")),  # serves "/metrics"
]

# URL patterns for standard Django admin interface.
urlpatterns += [
    path("api-auth/", include("rest_framework.urls")),
    path("admin/", admin.site.urls),
]

# URL patterns for general debugging.
urlpatterns += [
    path("error/", views.fake_error, name="internal-fake-error"),
]

# URL patterns for potentially-destructive custom commands.
urlpatterns += [
    path(
        "delete_cloud_accounts_not_in_sources/",
        views.delete_cloud_accounts_not_in_sources,
        name="internal-delete-cloud-accounts-not-in-sources",
    ),
    path(
        "recalculate_concurrent_usage/",
        views.recalculate_concurrent_usage,
        name="internal-recalculate-concurrent-usage",
    ),
    path("recalculate_runs/", views.recalculate_runs, name="internal-recalculate-runs"),
    path("sources_kafka/", views.sources_kafka, name="internal-sources-kafka"),
]

# URL patterns for accessing various models.
urlpatterns += [
    path("api/cloudigrade/v1/", include(router.urls)),
    path(
        "api/cloudigrade/v1/availability_status",
        views.availability_check,
        name="internal-availability-status",
    ),
    path(
        "api/cloudigrade/v1/problematic_runs/",
        views.ProblematicRunList.as_view(),
    ),
    path(
        "openapi.json",
        get_schema_view(
            title="Cloudigrade Internal API",
            renderer_classes=[renderers.JSONOpenAPIRenderer],
            permission_classes=[permissions.AllowAny],
            authentication_classes=[],
            public=True,
            url="/internal/",
            urlconf="internal.urls",
        ),
        name="openapi-schema-internal",
    ),
]
