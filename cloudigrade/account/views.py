"""DRF API views for the account app."""
from rest_framework import viewsets, mixins, status, exceptions
from rest_framework.response import Response

from account import serializers
from account.models import Account


class AccountViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    """
    List all, retrieve a single, or create a customer Account.

    Do not allow to update, replace, or delete an Account.
    """

    queryset = Account.objects.all()
    serializer_class = serializers.AccountSerializer


class ReportViewSet(viewsets.ViewSet):
    """Generate a usage report."""

    serializer_class = serializers.ReportSerializer

    def create(self, request, *args, **kwargs):
        """Create the usage report and return the results."""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = serializer.create()
        except Account.DoesNotExist:
            raise exceptions.NotFound()
        return Response(result, status=status.HTTP_200_OK)
