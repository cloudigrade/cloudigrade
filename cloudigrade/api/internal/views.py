"""Internal views for cloudigrade API."""

from django.contrib.auth.models import User
from django_filters import rest_framework as django_filters
from rest_framework import exceptions, mixins, permissions, status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    authentication_classes,
    permission_classes,
    schema,
)
from rest_framework.response import Response

from api import models
from api.authentication import (
    IdentityHeaderAuthenticationInternal,
    IdentityHeaderAuthenticationInternalCreateUser,
)
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.internal import filters, serializers
from api.serializers import CloudAccountSerializer
from api.views import AccountViewSet


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def availability_check(request):
    """
    Attempt to re-enable cloudigrade accounts with matching source_id.

    This is an internal only API, so we do not want it to be in the openapi.spec.
    """
    data = request.data
    source_id = data.get("source_id")
    if not source_id:
        raise exceptions.ValidationError(detail="source_id field is required")

    cloudaccounts = models.CloudAccount.objects.filter(platform_source_id=source_id)
    for cloudaccount in cloudaccounts:
        cloudaccount.enable()

    return Response(status=status.HTTP_204_NO_CONTENT)


class InternalViewSetMixin:
    """Mixin of common attributes for our internal ViewSet classes."""

    authentication_classes = [IdentityHeaderAuthenticationInternal]
    permission_classes = [permissions.AllowAny]
    filter_backends = [django_filters.DjangoFilterBackend]
    schema = None


class InternalAccountViewSet(
    InternalViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    AccountViewSet,
):
    """
    Create, retrieve, update, delete, or list AwsCloudAccounts for internal use.

    Unlike most of our other internal ViewSets, this one extends our existing public
    AccountViewSet in order to move our "legacy" writable API for accounts out of the
    public space and into the internal space.

    This ViewSet uses custom permission and authentication handling to force only the
    "create" action (from HTTP POST) to have a proper User from the identity header. We
    need that authenticated User in order to create the CloudAccount object.
    """

    queryset = models.CloudAccount.objects.all()
    serializer_class = CloudAccountSerializer

    def get_permissions(self):
        """Instantiate and return the list of permissions that this view requires."""
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = self.permission_classes
        return [permission() for permission in permission_classes]

    def get_authenticators(self):
        """Instantiate and return the list of authenticators that this view can use."""
        # Note: We can't use .action like get_permissions because get_authenticators is
        # called from initialize_request *before* .action is set on the request object.
        if self.request.method.lower() == "post":
            authentication_classes = [IdentityHeaderAuthenticationInternalCreateUser]
        else:
            authentication_classes = self.authentication_classes
        return [auth() for auth in authentication_classes]


class InternalUserViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Users for internal use."""

    queryset = User.objects.all()
    serializer_class = serializers.InternalUserSerializer
    filterset_fields = {
        "username": ["exact"],
        "date_joined": ["lt", "exact", "gt"],
    }


class InternalUserTaskLockViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list UserTaskLocks for internal use."""

    queryset = models.UserTaskLock.objects.all()
    serializer_class = serializers.InternalUserTaskLockSerializer
    filterset_fields = {
        "user": ["exact"],
        "locked": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalCloudAccountViewSet(
    InternalViewSetMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve, delete, or list CloudAccounts for internal use."""

    queryset = models.CloudAccount.objects.all()
    serializer_class = serializers.InternalCloudAccountSerializer
    filterset_class = filters.InternalCloudAccountFilterSet


class InternalInstanceViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Instances for internal use."""

    queryset = models.Instance.objects.all()
    serializer_class = serializers.InternalInstanceSerializer
    filterset_class = filters.InternalInstanceFilterSet


class InternalInstanceEventViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list InstanceEvents for internal use."""

    queryset = models.InstanceEvent.objects.all()
    serializer_class = serializers.InternalInstanceEventSerializer
    filterset_fields = {
        "event_type": ["exact"],
        "instance": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalMachineImageViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve, reinspect, or list MachineImages for internal use."""

    queryset = models.MachineImage.objects.all()
    serializer_class = serializers.InternalMachineImageSerializer
    filterset_fields = {
        "architecture": ["exact"],
        "name": ["exact"],
        "status": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }

    @action(detail=True, methods=["post"])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        machine_image = self.get_object()
        machine_image.status = models.MachineImage.PENDING
        machine_image.save()

        serializer = serializers.InternalMachineImageSerializer(
            machine_image, context={"request": request}
        )

        return Response(serializer.data)


class InternalRunViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Runs for internal use."""

    queryset = models.Run.objects.all()
    serializer_class = serializers.InternalRunSerializer
    filterset_class = filters.InternalRunFilterSet


class InternalMachineImageInspectionStartViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list MachineImageInspectionStarts for internal use."""

    queryset = models.MachineImageInspectionStart.objects.all()
    serializer_class = serializers.InternalMachineImageInspectionStartSerializer
    filterset_fields = {
        "machineimage": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalConcurrentUsageViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.ConcurrentUsage.objects.all()
    serializer_class = serializers.InternalConcurrentUsageSerializer
    filterset_class = filters.InternalConcurrentUsageFilterSet


class InternalConcurrentUsageCalculationTaskViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsageCalculationTasks for internal use."""

    queryset = models.ConcurrentUsageCalculationTask.objects.all()
    serializer_class = serializers.InternalConcurrentUsageCalculationTaskSerializer
    filterset_fields = {
        "status": ["exact"],
        "user": ["exact"],
        "task_id": ["exact"],
        "date": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalInstanceDefinitionViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.InstanceDefinition.objects.all()
    serializer_class = serializers.InternalInstanceDefinitionSerializer
    filterset_fields = {
        "cloud_type": ["exact"],
        "instance_type": ["exact"],
        "memory": ["exact"],
        "vcpu": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsCloudAccountViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsCloudAccount for internal use."""

    queryset = aws_models.AwsCloudAccount.objects.all()
    serializer_class = serializers.InternalAwsCloudAccountSerializer
    filterset_class = filters.InternalAwsCloudAccountFilterSet


class InternalAwsInstanceViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsInstances for internal use."""

    queryset = aws_models.AwsInstance.objects.all()
    serializer_class = serializers.InternalAwsInstanceSerializer
    filterset_fields = {
        "ec2_instance_id": ["exact"],
        "region": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsInstanceEventViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsInstanceEvents for internal use."""

    queryset = aws_models.AwsInstanceEvent.objects.all()
    serializer_class = serializers.InternalAwsInstanceEventSerializer
    filterset_fields = {
        "subnet": ["exact"],
        "instance_type": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsMachineImageViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsMachineImages for internal use."""

    queryset = aws_models.AwsMachineImage.objects.all()
    serializer_class = serializers.InternalAwsMachineImageSerializer
    filterset_fields = {
        "ec2_ami_id": ["exact"],
        "platform": ["exact"],
        "owner_aws_account_id": ["exact"],
        "region": ["exact"],
        "aws_marketplace_image": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsMachineImageCopyViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsMachineImageCopies for internal use."""

    queryset = aws_models.AwsMachineImageCopy.objects.all()
    serializer_class = serializers.InternalAwsMachineImageCopySerializer
    filterset_fields = {
        "reference_awsmachineimage": ["exact"],
        "ec2_ami_id": ["exact"],
        "platform": ["exact"],
        "owner_aws_account_id": ["exact"],
        "region": ["exact"],
        "aws_marketplace_image": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAzureCloudAccountViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureCloudAccount.objects.all()
    serializer_class = serializers.InternalAzureCloudAccountSerializer
    filterset_class = filters.InternalAzureCloudAccountFilterSet


class InternalAzureInstanceViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AzureInstanceEvents for internal use."""

    queryset = azure_models.AzureInstance.objects.all()
    serializer_class = serializers.InternalAzureInstanceSerializer
    filterset_fields = {
        "region": ["exact"],
        "resource_id": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAzureInstanceEventViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureInstanceEvents for internal use."""

    queryset = azure_models.AzureInstanceEvent.objects.all()
    serializer_class = serializers.InternalAzureInstanceEventSerializer
    filterset_fields = {
        "instance_type": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAzureMachineImageViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureMachineImage.objects.all()
    serializer_class = serializers.InternalAzureMachineImageSerializer
    filterset_fields = {
        "azure_marketplace_image": ["exact"],
        "region": ["exact"],
        "resource_id": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
