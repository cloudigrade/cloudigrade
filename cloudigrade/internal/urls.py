"""Internal API URL configuration for cloudigrade."""
from django.contrib import admin
from django.urls import include, path
from rest_framework import routers

from internal import views as internal_views

internal_router = routers.DefaultRouter()

# URLs for slightly different internal versions of public viewset routes.
internal_router.register(
    r"accounts", internal_views.InternalAccountViewSet, basename="internal-account"
)

# URLs for common models
internal_router.register(
    r"users", internal_views.InternalUserViewSet, basename="internal-user"
)
internal_router.register(
    r"usertasklocks",
    internal_views.InternalUserTaskLockViewSet,
    basename="internal-usertasklock",
)
internal_router.register(
    r"cloudaccounts",
    internal_views.InternalCloudAccountViewSet,
    basename="internal-cloudaccount",
)
internal_router.register(
    r"instances",
    internal_views.InternalInstanceViewSet,
    basename="internal-instance",
)
internal_router.register(
    r"instanceevents",
    internal_views.InternalInstanceEventViewSet,
    basename="internal-instanceevent",
)
internal_router.register(
    r"machineimages",
    internal_views.InternalMachineImageViewSet,
    basename="internal-machineimage",
)
internal_router.register(
    r"runs", internal_views.InternalRunViewSet, basename="internal-run"
)
internal_router.register(
    r"machineimageinspectionstarts",
    internal_views.InternalMachineImageInspectionStartViewSet,
    basename="internal-machineimageinspectionstart",
)
internal_router.register(
    r"concurrentusages",
    internal_views.InternalConcurrentUsageViewSet,
    basename="internal-concurrentusage",
)
internal_router.register(
    r"concurrentusagecalculationtasks",
    internal_views.InternalConcurrentUsageCalculationTaskViewSet,
    basename="internal-concurrentusagecalculationtask",
)
internal_router.register(
    r"instancedefinitions",
    internal_views.InternalInstanceDefinitionViewSet,
    basename="internal-instancedefinition",
)
# URLs for AWS models
internal_router.register(
    r"awscloudaccounts",
    internal_views.InternalAwsCloudAccountViewSet,
    basename="internal-awscloudaccount",
)
internal_router.register(
    r"awsinstances",
    internal_views.InternalAwsInstanceViewSet,
    basename="internal-awsinstance",
)
internal_router.register(
    r"awsmachineimages",
    internal_views.InternalAwsMachineImageViewSet,
    basename="internal-awsmachineimage",
)
internal_router.register(
    r"awsmachineimagecopies",
    internal_views.InternalAwsMachineImageCopyViewSet,
    basename="internal-awsmachineimagecopy",
)
internal_router.register(
    r"awsinstanceevents",
    internal_views.InternalAwsInstanceEventViewSet,
    basename="internal-awsinstanceevent",
)
# URLs for Azure models
internal_router.register(
    r"azurecloudaccounts",
    internal_views.InternalAzureCloudAccountViewSet,
    basename="internal-azurecloudaccount",
)
internal_router.register(
    r"azureinstances",
    internal_views.InternalAzureInstanceViewSet,
    basename="internal-azureinstance",
)
internal_router.register(
    r"azuremachineimages",
    internal_views.InternalAzureMachineImageViewSet,
    basename="internal-azuremachineimage",
)
internal_router.register(
    r"azureinstanceevents",
    internal_views.InternalAzureInstanceEventViewSet,
    basename="internal-azureinstanceevent",
)

urlpatterns = [
    path("api-auth/", include("rest_framework.urls")),
    path("healthz/", include("health_check.urls")),
    path("admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),
    path("api/cloudigrade/v1/", include(internal_router.urls)),
    path("api/cloudigrade/v1/", internal_views.availability_check),
]
