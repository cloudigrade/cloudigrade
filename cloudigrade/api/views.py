"""Public views for cloudigrade API."""
from datetime import timedelta

from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django_filters import rest_framework as django_filters
from rest_framework import exceptions, mixins, permissions, viewsets
from rest_framework.response import Response

from api import filters, models, serializers
from api import schemas
from api.authentication import IdentityHeaderAuthenticationUserNotRequired
from api.serializers import DailyConcurrentUsageDummyQueryset
from util.aws.sts import _get_primary_account_id, cloudigrade_policy
from util.misc import get_today


class AccountViewSet(viewsets.ReadOnlyModelViewSet):
    """List all or retrieve a single cloud account."""

    schema = schemas.DescriptiveAutoSchema("cloud account", tags=["api-v2"])
    serializer_class = serializers.CloudAccountSerializer
    queryset = models.CloudAccount.objects.all()
    filter_backends = (
        django_filters.DjangoFilterBackend,
        filters.CloudAccountRequestIsUserFilterBackend,
    )


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """List all or retrieve a single instance."""

    schema = schemas.DescriptiveAutoSchema("instance", tags=["api-v2"])
    serializer_class = serializers.InstanceSerializer
    queryset = models.Instance.objects.all()
    filter_backends = (
        django_filters.DjangoFilterBackend,
        filters.InstanceRequestIsUserFilterBackend,
    )
    filterset_class = filters.InstanceFilterSet


class MachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """List all or retrieve a single machine image."""

    schema = schemas.DescriptiveAutoSchema("image", tags=["api-v2"])
    serializer_class = serializers.MachineImageSerializer
    queryset = models.MachineImage.objects.all()
    filter_backends = (
        django_filters.DjangoFilterBackend,
        filters.MachineImageRequestIsUserFilterBackend,
    )
    filterset_fields = ("architecture", "status")


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
            "version": settings.CLOUDIGRADE_VERSION,
        }
        return Response(response)


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class DailyConcurrentUsageViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    """
    Generate report of concurrent usage within a time frame.

    This viewset has to be wrapped in a non_atomic_requests decorator. DRF by default
    runs viewset methods inside of an atomic transaction. But in this case we have to
    create ConcurrentUsageCalculationTask to schedule jobs even when we raise a
    ResultsUnavailable 425 exception.
    """

    schema = schemas.ConcurrentSchema(tags=["api-v2"])
    serializer_class = serializers.DailyConcurrentUsageSerializer

    def get_queryset(self):  # noqa: C901
        """Get the queryset of dates filtered to the appropriate inputs."""
        user = self.request.user
        errors = {}
        tomorrow = get_today() + timedelta(days=1)
        try:
            start_date = self.request.query_params.get("start_date", None)
            start_date = parse(start_date).date() if start_date else get_today()
            # Start date is inclusive, if start date is tomorrow or after,
            # we do not return anything
            if start_date >= tomorrow:
                errors["start_date"] = [_("start_date cannot be in the future.")]
        except ValueError:
            errors["start_date"] = [_("start_date must be a date (YYYY-MM-DD).")]

        try:
            end_date = self.request.query_params.get("end_date", None)
            # End date is noninclusive, set it to tomorrow if one is not provided
            end_date = parse(end_date).date() if end_date else tomorrow
            # If end date is after tomorrow, we do not return anything
            if end_date > tomorrow:
                errors["end_date"] = [_("end_date cannot be in the future.")]
            if end_date <= user.date_joined.date():
                errors["end_date"] = [_("end_date must be after user creation date.")]
        except ValueError:
            errors["end_date"] = [_("end_date must be a date (YYYY-MM-DD).")]

        if errors:
            raise exceptions.ValidationError(errors)

        queryset = DailyConcurrentUsageDummyQueryset(start_date, end_date, user.id)
        return queryset
