"""Public viewset classes for cloudigrade API."""

from django.conf import settings
from django.urls import reverse
from django_filters import rest_framework as django_filters
from rest_framework import permissions, viewsets
from rest_framework.response import Response

from api import filters, models, serializers
from api import schemas
from api.authentication import IdentityHeaderAuthenticationUserNotRequired
from util.aws.sts import _get_primary_account_id, cloudigrade_policy
from util.azure import ARM_TEMPLATE


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """List all or retrieve a single cloud account."""

    schema = schemas.DescriptiveAutoSchema("cloud account", tags=["api-v2"])
    serializer_class = serializers.CloudAccountSerializer
    queryset = models.CloudAccount.objects.all()
    filter_backends = (
        django_filters.DjangoFilterBackend,
        filters.CloudAccountRequestIsUserFilterBackend,
    )


class SysconfigViewSet(viewsets.ViewSet):
    """Retrieve dynamic sysconfig data including cloud-specific IDs and policies."""

    authentication_classes = [IdentityHeaderAuthenticationUserNotRequired]
    permission_classes = [permissions.AllowAny]
    schema = schemas.SysconfigSchema(tags=["api-v2"])

    def list(self, *args, **kwargs):
        """Get cloud account ids currently used by this installation."""
        response = {
            "aws_account_id": _get_primary_account_id(),
            "aws_policies": {
                "traditional_inspection": cloudigrade_policy,
            },
            "azure_offer_template_path": reverse("v2-azure-offer-list"),
            "version": settings.CLOUDIGRADE_VERSION,
        }
        return Response(response)


class AzureOfferTemplateViewSet(viewsets.ViewSet):
    """Generate and serve Azure offer template based on current state."""

    # We intentionally require no authentication here as this
    # endpoint needs to be public and accessible by Azure.
    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    schema = schemas.AzureOfferTemplateSchema(tags=["api-v2"])

    def list(self, *args, **kwargs):
        """Get ARM offer template populated with ids used by this installation."""
        return Response(ARM_TEMPLATE, headers={"Access-Control-Allow-Origin": "*"})
