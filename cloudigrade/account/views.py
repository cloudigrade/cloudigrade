"""DRF API views for the account app."""
from rest_framework import exceptions, mixins, status, viewsets
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
            result = serializer.create()
        except Account.DoesNotExist:
            raise exceptions.NotFound()
        return Response(result, status=status.HTTP_200_OK)
