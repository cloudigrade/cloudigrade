"""Internal API URL configuration for cloudigrade."""
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from internal import views

# Prepare a list of DRF ViewSet routes.
routes = []

# URLs for slightly different internal versions of public viewset routes.
routes += [
    ("accounts", views.InternalAccountViewSet, "account"),
]

# URLs for common models
# "None" for the third tuple value means to use the model's name.
routes += [
    ("users", views.InternalUserViewSet, "user"),
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
    (
        "concurrentusagecalculationtasks",
        views.InternalConcurrentUsageCalculationTaskViewSet,
        None,
    ),
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

# Register all the DRF ViewSet routes with a common "internal-" basename prefix.
router = routers.DefaultRouter()
for (prefix, viewset, basename) in routes:
    if not basename:
        basename = router.get_default_basename(viewset)
    basename = f"internal-{basename}"
    router.register(prefix, viewset, basename=basename)

urlpatterns = [
    path("api-auth/", include("rest_framework.urls")),
    path("healthz/", include("health_check.urls")),
    path("admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),
    path("api/cloudigrade/v1/", include(router.urls)),
    path("api/cloudigrade/v1/", views.availability_check),
]
