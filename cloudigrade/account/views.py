"""DRF API views for the account app."""
from django.utils.translation import gettext as _

from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from account import serializers
from account.exceptions import InvalidCloudProviderError
from account.models import (Account,
                            AwsAccount,
                            Instance)


def convert_param_to_int(name, value):
    """Check if a value is convertable to int.

    :param name: The field name being validated
    :param value: The value to convert to int
    :returns: The int value
    "raises: ValidationError if value not convertable
        to an int
    """
    if isinstance(value, int):
        return value

    try:
        return int(value)
    except ValueError:
        error = {
            name: [_('The id must be an integer.')]
        }
        raise ValidationError(error)


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
    accounts = Account.objects.all()
    serializer_class = serializers.InstancePolymorphicSerializer

    def get_queryset(self):
        """Get the queryset filtered to appropriate user."""
        user = self.request.user
        if not user.is_superuser:
            accounts = self.accounts.filter(user=user)
            account_ids = [account.id for account in accounts]
            return self.queryset.filter(pk__in=account_ids)
        user_id = self.request.query_params.get('user_id', None)
        if user_id is not None:
            user_id = convert_param_to_int('user_id', user_id)
            accounts = self.accounts.filter(user__id=int(user_id))
            account_ids = [account.id for account in accounts]
            return self.queryset.filter(pk__in=account_ids)

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
