"""DRF API views for the account app."""
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.response import Response

from account import serializers
from account.exceptions import InvalidCloudProviderError
from account.models import (Account,
                            AwsAccount,
                            Instance,
                            InstanceEvent,
                            MachineImage)
from account.util import convert_param_to_int


class AccountViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """
    List all, retrieve a single, or create a customer account.

    Do not allow to update, replace, or delete an account at this view because
    we currently **only** allow accounts to be created or retrieved.
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


class ReportViewSet(viewsets.ViewSet):
    """Generate a usage report."""

    serializer_class = serializers.ReportSerializer

    def list(self, request, *args, **kwargs):
        """
        Create the usage report and return the results.

        Note: this is called "list" to simplify DRF router integration. By
        using the "list" name, this method automatically gets mapped to the
        GET handler for the "/" end of the URI (effectively "/api/v1/report/").
        """
        serializer = self.serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            result = serializer.generate()
        except AwsAccount.DoesNotExist:
            raise exceptions.NotFound()
        except InvalidCloudProviderError as e:
            raise exceptions.ValidationError(detail=str(e))
        return Response(result, status=status.HTTP_200_OK)
