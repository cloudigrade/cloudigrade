"""Internal views for cloudigrade API."""

from django.contrib.auth.models import User
from django_filters import rest_framework as django_filters
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, schema
from rest_framework.response import Response

from api import models
from api.authentication import ThreeScaleAuthenticationNoOrgAdmin
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.internal import filters, serializers


@api_view(["POST"])
@authentication_classes([ThreeScaleAuthenticationNoOrgAdmin])
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


class InternalUserViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Users for internal use."""

    queryset = User.objects.all()
    serializer_class = serializers.InternalUserSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "username": ["exact"],
        "date_joined": ["lt", "exact", "gt"],
    }
    schema = None


class InternalUserTaskLockViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list UserTaskLocks for internal use."""

    queryset = models.UserTaskLock.objects.all()
    serializer_class = serializers.InternalUserTaskLockSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "user": ["exact"],
        "locked": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalCloudAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list CloudAccounts for internal use."""

    queryset = models.CloudAccount.objects.all()
    serializer_class = serializers.InternalCloudAccountSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_class = filters.InternalCloudAccountFilterSet
    schema = None


class InternalInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Instances for internal use."""

    queryset = models.Instance.objects.all()
    serializer_class = serializers.InternalInstanceSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_class = filters.InternalInstanceFilterSet
    schema = None


class InternalInstanceEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list InstanceEvents for internal use."""

    queryset = models.InstanceEvent.objects.all()
    serializer_class = serializers.InternalInstanceEventSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "event_type": ["exact"],
        "instance": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalMachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve, reinspect, or list MachineImages for internal use."""

    queryset = models.MachineImage.objects.all()
    serializer_class = serializers.InternalMachineImageSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "architecture": ["exact"],
        "name": ["exact"],
        "status": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None

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


class InternalRunViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Runs for internal use."""

    queryset = models.Run.objects.all()
    serializer_class = serializers.InternalRunSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_class = filters.InternalRunFilterSet
    schema = None


class InternalMachineImageInspectionStartViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list MachineImageInspectionStarts for internal use."""

    queryset = models.MachineImageInspectionStart.objects.all()
    serializer_class = serializers.InternalMachineImageInspectionStartSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "machineimage": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalConcurrentUsageViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.ConcurrentUsage.objects.all()
    serializer_class = serializers.InternalConcurrentUsageSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_class = filters.InternalConcurrentUsageFilterSet
    schema = None


class InternalConcurrentUsageCalculationTaskViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list ConcurrentUsageCalculationTasks for internal use."""

    queryset = models.ConcurrentUsageCalculationTask.objects.all()
    serializer_class = serializers.InternalConcurrentUsageCalculationTaskSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "status": ["exact"],
        "user": ["exact"],
        "task_id": ["exact"],
        "date": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalInstanceDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.InstanceDefinition.objects.all()
    serializer_class = serializers.InternalInstanceDefinitionSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "cloud_type": ["exact"],
        "instance_type": ["exact"],
        "memory": ["exact"],
        "vcpu": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalAwsCloudAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsCloudAccount for internal use."""

    queryset = aws_models.AwsCloudAccount.objects.all()
    serializer_class = serializers.InternalAwsCloudAccountSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_class = filters.InternalAwsCloudAccountFilterSet
    schema = None


class InternalAwsInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsInstances for internal use."""

    queryset = aws_models.AwsInstance.objects.all()
    serializer_class = serializers.InternalAwsInstanceSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "ec2_instance_id": ["exact"],
        "region": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalAwsInstanceEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsInstanceEvents for internal use."""

    queryset = aws_models.AwsInstanceEvent.objects.all()
    serializer_class = serializers.InternalAwsInstanceEventSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "subnet": ["exact"],
        "instance_type": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalAwsMachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsMachineImages for internal use."""

    queryset = aws_models.AwsMachineImage.objects.all()
    serializer_class = serializers.InternalAwsMachineImageSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "ec2_ami_id": ["exact"],
        "platform": ["exact"],
        "owner_aws_account_id": ["exact"],
        "region": ["exact"],
        "aws_marketplace_image": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalAwsMachineImageCopyViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsMachineImageCopies for internal use."""

    queryset = aws_models.AwsMachineImageCopy.objects.all()
    serializer_class = serializers.InternalAwsMachineImageCopySerializer
    filter_backends = [django_filters.DjangoFilterBackend]
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
    schema = None


class InternalAzureCloudAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureCloudAccount.objects.all()
    serializer_class = serializers.InternalAzureCloudAccountSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_class = filters.InternalAzureCloudAccountFilterSet
    schema = None


class InternalAzureInstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AzureInstanceEvents for internal use."""

    queryset = azure_models.AzureInstance.objects.all()
    serializer_class = serializers.InternalAzureInstanceSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "region": ["exact"],
        "resource_id": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalAzureInstanceEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AzureInstanceEvents for internal use."""

    queryset = azure_models.AzureInstanceEvent.objects.all()
    serializer_class = serializers.InternalAzureInstanceEventSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "instance_type": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None


class InternalAzureMachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureMachineImage.objects.all()
    serializer_class = serializers.InternalAzureMachineImageSerializer
    filter_backends = [django_filters.DjangoFilterBackend]
    filterset_fields = {
        "azure_marketplace_image": ["exact"],
        "region": ["exact"],
        "resource_id": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
    schema = None
