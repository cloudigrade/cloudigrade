"""Internal viewset classes for cloudigrade API."""
from datetime import timedelta

from django.utils.translation import gettext as _
from django_celery_beat.models import PeriodicTask
from django_filters import rest_framework as django_filters
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action, schema
from rest_framework.response import Response

from api import models, schemas, tasks
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.models import User
from api.serializers import CloudAccountSerializer
from api.viewsets import AccountViewSet, DailyConcurrentUsageViewSet
from internal import filters, serializers
from internal.authentication import (
    IdentityHeaderAuthenticationInternal,
    IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader,
    IdentityHeaderAuthenticationInternalCreateUser,
)
from util.misc import get_today


class InternalViewSetMixin:
    """Mixin of common attributes for our internal ViewSet classes."""

    authentication_classes = [IdentityHeaderAuthenticationInternal]
    permission_classes = [permissions.AllowAny]
    filter_backends = [django_filters.DjangoFilterBackend]


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
    schema = schemas.DescriptiveAutoSchema(
        "cloud account",
        custom_responses={"DELETE": {"202": {"description": ""}}},
        operation_id_base="Account",
    )
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

    def destroy(self, request, *args, **kwargs):
        """Destroy the CloudAccount but return 202 instead of 204."""
        response = super(InternalAccountViewSet, self).destroy(request, *args, **kwargs)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            response = Response(
                data=response.data,
                status=status.HTTP_202_ACCEPTED,
                template_name=response.template_name,
                content_type=response.content_type,
            )
        return response

    def perform_destroy(self, instance):
        """Delay an async task to destroy the instance."""
        tasks.delete_cloud_account.delay(instance.id)


class InternalUserViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Users for internal use."""

    queryset = User.objects.all()
    serializer_class = serializers.InternalUserSerializer
    filterset_fields = {
        "account_number": ["exact"],
        "org_id": ["exact"],
        "date_joined": ["lt", "exact", "gt"],
    }


class InternalUserTaskLockViewSet(
    InternalViewSetMixin,
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Retrieve, delete, or list UserTaskLocks for internal use."""

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
    filterset_class = filters.InternalInstanceEventFilterSet


class InternalMachineImageViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve, reinspect, or list MachineImages for internal use."""

    queryset = models.MachineImage.objects.all()
    serializer_class = serializers.InternalMachineImageSerializer
    filterset_fields = {
        "architecture": ["exact"],
        "object_id": ["exact"],
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


class InternalInstanceDefinitionViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.InstanceDefinition.objects.all()
    serializer_class = serializers.InternalInstanceDefinitionSerializer
    filterset_fields = {
        "cloud_type": ["exact"],
        "instance_type": ["exact"],
        "memory_mib": ["exact"],
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


class InternalDailyConcurrentUsageViewSet(DailyConcurrentUsageViewSet):
    """Generate report of concurrent usage within a time frame."""

    def get_authenticators(self):
        """Instantiate and return the list of authenticators that this view can use."""
        authentication_classes = [
            IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader
        ]
        return [auth() for auth in authentication_classes]

    def latest_start_date(self):
        """Return the latest allowed start_date."""
        return get_today()

    def latest_end_date(self):
        """Return the latest allowed end_date."""
        return get_today() + timedelta(days=1)

    def late_start_date_error(self):
        """Return the error message for specifying a late start_date."""
        return _("start_date cannot be in the future.")


@schema(None)
class InternalPeriodicTaskViewSet(
    InternalViewSetMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve, update, or list PeriodicTasks for internal use."""

    queryset = PeriodicTask.objects.all()
    serializer_class = serializers.InternalPeriodicTaskSerializer


class InternalSyntheticDataRequestViewSet(InternalViewSetMixin, viewsets.ModelViewSet):
    """Create, retrieve, update, delete, or list SyntheticDataRequests."""

    queryset = models.SyntheticDataRequest.objects.all()
    serializer_class = serializers.InternalSyntheticDataRequestSerializer
    filterset_fields = {
        "user_id": ["exact"],
        "expires_at": ["lt", "exact", "gt"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }
