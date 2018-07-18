"""DRF API views for the account app."""
from django.contrib.auth import get_user_model
from django.http import HttpResponseForbidden, HttpResponseNotFound
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from account import serializers
from account.models import (Account,
                            Instance,
                            InstanceEvent,
                            MachineImage,
                            User)
from account.util import convert_param_to_int
from util.aws.sts import _get_primary_account_id


class AccountViewSet(mixins.CreateModelMixin,
                     mixins.RetrieveModelMixin,
                     mixins.UpdateModelMixin,
                     mixins.ListModelMixin,
                     viewsets.GenericViewSet):
    """
    Create, retrieve, update, or list customer accounts.

    Do not allow to delete an account at this view because we have not yet
    defined how we want account "soft" deletion to behave.
    """

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


class MachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all or retrieve a single machine image.

    Do not allow to create, update, replace, or delete an image at
    this view because we currently **only** allow images to be retrieved.
    """

    queryset = MachineImage.objects.all()
    serializer_class = serializers.MachineImagePolymorphicSerializer

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


class SysconfigViewSet(viewsets.ViewSet):
    """View to display our cloud account ids."""

    def list(self, *args, **kwargs):
        """Get cloud account ids currently used by this installation."""
        response = {
            'aws_account_id': _get_primary_account_id()
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
        return Response(result, status=status.HTTP_200_OK)


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    """List all users and their basic metadata."""

    queryset = User.objects.all()
    serializer_class = serializers.UserSerializer

    def list(self, request, *args, **kwargs):
        """Get list of users and their basic metadata."""
        user = request.user
        if not user.is_superuser:
            return HttpResponseForbidden()
        users = get_user_model().objects.all().values(
            'id',
            'username',
            'is_superuser')
        return Response(users)

    def retrieve(self, request, pk=None):
        """Get a single user."""
        user = request.user
        if str(user.id) == pk:
            serializer = serializers.UserSerializer(user)
            return Response(serializer.data)

        if not user.is_superuser:
            return HttpResponseForbidden()
        user = get_user_model().objects.filter(id=pk).values(
            'id',
            'username',
            'is_superuser').first()
        if user is None:
            return HttpResponseNotFound()
        return Response(user)
