"""Internal API URL configuration for cloudigrade."""
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from internal import views

router = routers.DefaultRouter()

# URLs for slightly different internal versions of public viewset routes.
router.register("accounts", views.InternalAccountViewSet, "internal-account")

# URLs for common models
router.register("users", views.InternalUserViewSet, "internal-user")
router.register(
    "usertasklocks", views.InternalUserTaskLockViewSet, "internal-usertasklock"
)
router.register(
    "cloudaccounts", views.InternalCloudAccountViewSet, "internal-cloudaccount"
)
router.register("instances", views.InternalInstanceViewSet, "internal-instance")
router.register(
    "instanceevents", views.InternalInstanceEventViewSet, "internal-instanceevent"
)
router.register(
    "machineimages", views.InternalMachineImageViewSet, "internal-machineimage"
)
router.register(r"runs", views.InternalRunViewSet, "internal-run")
router.register(
    "machineimageinspectionstarts",
    views.InternalMachineImageInspectionStartViewSet,
    "internal-machineimageinspectionstart",
)
router.register(
    "concurrentusages", views.InternalConcurrentUsageViewSet, "internal-concurrentusage"
)
router.register(
    "concurrentusagecalculationtasks",
    views.InternalConcurrentUsageCalculationTaskViewSet,
    "internal-concurrentusagecalculationtask",
)
router.register(
    "instancedefinitions",
    views.InternalInstanceDefinitionViewSet,
    "internal-instancedefinition",
)
# URLs for AWS models
router.register(
    "awscloudaccounts", views.InternalAwsCloudAccountViewSet, "internal-awscloudaccount"
)
router.register(
    "awsinstances", views.InternalAwsInstanceViewSet, "internal-awsinstance"
)
router.register(
    "awsmachineimages", views.InternalAwsMachineImageViewSet, "internal-awsmachineimage"
)
router.register(
    "awsmachineimagecopies",
    views.InternalAwsMachineImageCopyViewSet,
    "internal-awsmachineimagecopy",
)
router.register(
    "awsinstanceevents",
    views.InternalAwsInstanceEventViewSet,
    "internal-awsinstanceevent",
)
# URLs for Azure models
router.register(
    "azurecloudaccounts",
    views.InternalAzureCloudAccountViewSet,
    "internal-azurecloudaccount",
)
router.register(
    "azureinstances", views.InternalAzureInstanceViewSet, "internal-azureinstance"
)
router.register(
    "azuremachineimages",
    views.InternalAzureMachineImageViewSet,
    "internal-azuremachineimage",
)
router.register(
    "azureinstanceevents",
    views.InternalAzureInstanceEventViewSet,
    "internal-azureinstanceevent",
)

urlpatterns = [
    path("api-auth/", include("rest_framework.urls")),
    path("healthz/", include("health_check.urls")),
    path("admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),
    path("api/cloudigrade/v1/", include(router.urls)),
    path("api/cloudigrade/v1/", views.availability_check),
]
