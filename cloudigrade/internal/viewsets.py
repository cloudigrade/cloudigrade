"""Internal viewset classes for cloudigrade API."""

from django_celery_beat.models import PeriodicTask
from django_filters import rest_framework as django_filters
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import schema
from rest_framework.response import Response

from api import models, schemas, tasks
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.models import User
from api.serializers import CloudAccountSerializer
from api.viewsets import AccountViewSet
from internal import filters, serializers
from internal.authentication import (
    IdentityHeaderAuthenticationInternal,
    IdentityHeaderAuthenticationInternalCreateUser,
)


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


class InternalUserViewSet(
    InternalViewSetMixin,
    viewsets.ModelViewSet,
):
    """Create, retrieve, update, delete or list an api.User for internal use."""

    queryset = User.objects.all()
    serializer_class = serializers.InternalUserSerializer
    filterset_class = filters.InternalUserFilterSet

    def destroy(self, request, *args, **kwargs):
        """Destroy the User only if it has no cloud accounts, otherwise return a 400."""
        user = self.get_object()
        if models.CloudAccount.objects.filter(user_id=user.id).exists():
            return Response(
                {
                    "error": f"User id {user.id} has related"
                    " CloudAccounts and cannot be deleted"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.delete(force=True)
        return Response(status=status.HTTP_202_ACCEPTED)


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


class InternalAwsCloudAccountViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsCloudAccount for internal use."""

    queryset = aws_models.AwsCloudAccount.objects.all()
    serializer_class = serializers.InternalAwsCloudAccountSerializer
    filterset_class = filters.InternalAwsCloudAccountFilterSet


class InternalAzureCloudAccountViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureCloudAccount.objects.all()
    serializer_class = serializers.InternalAzureCloudAccountSerializer
    filterset_class = filters.InternalAzureCloudAccountFilterSet


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
