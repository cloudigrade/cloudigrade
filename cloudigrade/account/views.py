"""DRF API views for the account app."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.http import HttpResponseNotFound
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from account import serializers
from account.models import (Account,
                            Instance,
                            InstanceEvent,
                            MachineImage)
from account.util import convert_param_to_int
from util.aws.sts import _get_primary_account_id, cloudigrade_policy
from util.permissions import IsSuperUser


class AccountViewSet(mixins.CreateModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     mixins.ListModelMixin,
                     mixins.DestroyModelMixin,
                     viewsets.GenericViewSet):
    """Create, retrieve, update, delete, or list customer accounts."""

    queryset = Account.objects.all()
    serializer_class = serializers.AccountPolymorphicSerializer

    def get_queryset(self):
        """Get the queryset filtered to appropriate user."""
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.filter(user=user)
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            return self.queryset.filter(user__id=user_id)
        return self.queryset


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all or retrieve a single instance.

    Do not allow to create, update, replace, or delete an instance at
    this view because we currently **only** allow instances to be retrieved.
    """

    queryset = Instance.objects.all()
    serializer_class = serializers.InstancePolymorphicSerializer

    def get_queryset(self):
        """Get the queryset filtered to appropriate user."""
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.filter(account__user__id=user.id)
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            return self.queryset.filter(account__user__id=user_id)
        return self.queryset


class InstanceEventViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all or retrieve a single instance event.

    Do not allow to create, update, replace, or delete an instance event at
    this view because we currently **only** allow instances to be retrieved.
    """

    queryset = InstanceEvent.objects.all()
    serializer_class = serializers.InstanceEventPolymorphicSerializer

    def get_queryset(self):
        """Get the queryset filtered to appropriate user."""
        user = self.request.user
        queryset = self.queryset
        if not user.is_superuser:
            queryset = queryset.filter(
                instance__account__user__id=user.id)
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            queryset = queryset.filter(
                instance__account__user__id=user_id)
        instance_id = self.request.query_params.get('instance_id', None)
        if instance_id is not None:
            instance_id = convert_param_to_int('instance_id', instance_id)
            queryset = queryset.filter(instance__id=instance_id)
        return queryset


class MachineImageViewSet(viewsets.ReadOnlyModelViewSet,
                          mixins.UpdateModelMixin):
    """List all, retrieve, or update a single machine image."""

    queryset = MachineImage.objects.all()
    serializer_class = serializers.MachineImagePolymorphicSerializer

    def get_queryset(self):
        """
        Get the queryset of MachineImages filtered to appropriate user.

        Superusers by default see *all* objects unfiltered, but a superuser may
        optionally provide a `user_id` argument in order to see what that user
        would normally see. This argument is ignored for normal users.

        Because users don't necessarily own the images they have been using, we
        have the filter join across instanceevent to instance to account so
        that we return the set of images that any of their instances have used.

        If we ever support archiving activity from specific accounts or
        instances, we will need to expand the conditions on this filter to
        exclude images used by archived instances (via archived accounts).
        """
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.filter(
                instanceevent__instance__account__user_id=user.id
            ).order_by('id').distinct()
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            return self.queryset.filter(
                instanceevent__instance__account__user_id=user_id
            ).order_by('id').distinct()
        return self.queryset.order_by('id')

    @action(detail=True, methods=['post'])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        user = self.request.user

        if not user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        machine_image = self.get_object()
        machine_image.status = MachineImage.PENDING
        machine_image.save()

        serializer = serializers.MachineImagePolymorphicSerializer(
            machine_image,
            context={'request': request}
        )

        return Response(serializer.data)


class SysconfigViewSet(viewsets.ViewSet):
    """View to display our cloud account ids."""

    def list(self, *args, **kwargs):
        """Get cloud account ids currently used by this installation."""
        response = {
            'aws_account_id': _get_primary_account_id(),
            'aws_policies': {
                'traditional_inspection': cloudigrade_policy,
            },
            'version': settings.CLOUDIGRADE_VERSION,
        }
        return Response(response)


class CloudAccountOverviewViewSet(viewsets.GenericViewSet):
    """Generate an object with a list of Cloud Accounts summary details."""

    serializer_class = serializers.CloudAccountOverviewSerializer

    def list(self, request, *args, **kwargs):
        """Get overview of accounts filtered to appropriate user."""
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = serializer.generate()
        return Response(result)


class DailyInstanceActivityViewSet(viewsets.GenericViewSet):
    """Generate a report of daily instance activity within a time frame."""

    serializer_class = serializers.DailyInstanceActivitySerializer

    def list(self, request, *args, **kwargs):
        """
        Run the daily instance activity report and return the results.

        Note: this is called "list" to simplify DRF router integration. By
        using the "list" name, this method automatically gets mapped to the
        GET handler for the "/" end of the URI (effectively "/api/v1/report/").
        """
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = serializer.generate()
        return Response(result)


class ImagesActivityOverviewViewSet(viewsets.GenericViewSet):
    """Generate report of images activity overviews within a time frame."""

    serializer_class = serializers.CloudAccountImagesSerializer

    def list(self, request, *args, **kwargs):
        """Get list of machine images filtered to appropriate account."""
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = serializer.generate()
        return Response(result)


class UserViewSet(viewsets.ViewSet):
    """List all users and their basic metadata."""

    permission_classes = (IsSuperUser,)

    def list(self, request):
        """
        Get list of users and their basic metadata.

        Note:
            Unfortunately, we have "noqa" statements in this function because
            the relationship for building the Q filter is so long. We tried a
            few variations in formatting, but they were all significantly less
            legible than keeping these on single long lines.
        """
        queryset = get_user_model().objects.all().annotate(
            accounts=Count('account', distinct=True),
            challenged_images=Count(
                'account__instance__instanceevent__machineimage', distinct=True, filter=(  # noqa: E501
                    Q(account__instance__instanceevent__machineimage__rhel_challenged=True) |  # noqa: E501
                    Q(account__instance__instanceevent__machineimage__openshift_challenged=True))),  # noqa: E501
        ).values('id', 'username', 'is_superuser', 'accounts',
                 'challenged_images')

        serializer = serializers.UserSerializer(queryset, many=True)

        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """
        Get a single user.

        Note:
            Unfortunately, we have "noqa" statements in this function because
            the relationship for building the Q filter is so long. We tried a
            few variations in formatting, but they were all significantly less
            legible than keeping these on single long lines.
        """
        # .annotate() only operates on a queryset, so we have to filter by
        # id first, and then grab the first (and only) result.
        user = get_user_model().objects.filter(id=pk).annotate(
            accounts=Count('account', distinct=True),
            challenged_images=Count(
                'account__instance__instanceevent__machineimage', distinct=True, filter=(  # noqa: E501
                    Q(account__instance__instanceevent__machineimage__rhel_challenged=True) |  # noqa: E501
                    Q(account__instance__instanceevent__machineimage__openshift_challenged=True)))  # noqa: E501
        ).values('id', 'username', 'is_superuser', 'accounts',
                 'challenged_images').first()

        if user is None:
            return HttpResponseNotFound()
        serializer = serializers.UserSerializer(user)

        return Response(serializer.data)
