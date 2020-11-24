"""Public views for cloudigrade API."""
from datetime import timedelta

from dateutil import tz
from dateutil.parser import parse
from django.conf import settings
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api import filters, models, serializers
from api.authentication import (
    ThreeScaleAuthentication,
)
from api.schemas import ConcurrentSchema, SysconfigSchema
from api.serializers import DailyConcurrentUsageDummyQueryset
from api.util import convert_param_to_int
from util.aws.sts import _get_primary_account_id, cloudigrade_policy
from util.misc import get_today


class AccountViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    Create, retrieve, update, delete, or list customer accounts.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.CloudAccountSerializer
    queryset = models.CloudAccount.objects.all()

    def get_queryset(self):
        """Get the Account queryset with filters applied."""
        user = self.request.user
        query_params = self.request.query_params
        user_id = convert_param_to_int("user_id", query_params.get("user_id", None))
        return filters.cloudaccounts(self.queryset, user_id, user)


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all or retrieve a single instance.

    Authenticate via 3scale.
    Do not allow to create, update, replace, or delete an instance at
    this view because we currently **only** allow instances to be retrieved.
    """

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.InstanceSerializer
    queryset = models.Instance.objects.all()

    def get_queryset(self):
        """Get the Instance queryset with filters applied."""
        user = self.request.user
        query_params = self.request.query_params

        user_id = convert_param_to_int("user_id", query_params.get("user_id", None))

        running_since = query_params.get("running_since", None)
        if running_since is not None:
            running_since = parse(running_since)
        if running_since and not running_since.tzinfo:
            running_since = running_since.replace(tzinfo=tz.tzutc())

        return filters.instances(self.queryset, user_id, running_since, user)


class MachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all, or retrieve a single machine image.

    Authenticate via 3scale.
    Do not allow to create, update, replace, or delete an machine image at
    this view.
    """

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.MachineImageSerializer
    queryset = models.MachineImage.objects.all()

    def get_queryset(self):
        """
        Get the MachineImage queryset filtered to appropriate user.

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
        query_params = self.request.query_params
        architecture = query_params.get("architecture", None)
        status = query_params.get("status", None)
        user_id = convert_param_to_int("user_id", query_params.get("user_id", None))
        return filters.machineimages(self.queryset, architecture, status, user_id, user)

    @action(detail=True, methods=["post"])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        user = self.request.user

        if not user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        machine_image = self.get_object()
        machine_image.status = models.MachineImage.PENDING
        machine_image.save()

        serializer = serializers.MachineImageSerializer(
            machine_image, context={"request": request}
        )

        return Response(serializer.data)


class SysconfigViewSet(viewsets.ViewSet):
    """
    View to display our cloud account ids.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication,)
    schema = SysconfigSchema()

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

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.DailyConcurrentUsageSerializer
    schema = ConcurrentSchema()

    def get_queryset(self):  # noqa: C901
        """Get the queryset of dates filtered to the appropriate inputs."""
        errors = {}
        try:
            start_date = self.request.query_params.get("start_date", None)
            start_date = parse(start_date).date() if start_date else get_today()
        except ValueError:
            errors["start_date"] = [_("start_date must be a date (YYYY-MM-DD).")]

        try:
            end_date = self.request.query_params.get("end_date", None)
            end_date = (
                parse(end_date).date() if end_date else get_today() + timedelta(days=1)
            )
        except ValueError:
            errors["end_date"] = [_("end_date must be a date (YYYY-MM-DD).")]

        user = self.request.user
        if not user.is_superuser:
            user_id = user.id
        else:
            try:
                user_id = convert_param_to_int(
                    "user_id", self.request.query_params.get("user_id", None)
                )
            except exceptions.ValidationError as e:
                errors.update(e.detail)

        if errors:
            raise exceptions.ValidationError(errors)

        queryset = DailyConcurrentUsageDummyQueryset(start_date, end_date, user_id)
        return queryset
