"""DRF API views for the account app v2."""
from datetime import timedelta

from dateutil import tz
from dateutil.parser import parse
from django.conf import settings
from django.db.models import Max
from django.utils.translation import gettext as _
from rest_framework import exceptions, mixins, status, viewsets
from rest_framework.decorators import action, api_view, schema
from rest_framework.response import Response

from api import serializers
from api.authentication import ThreeScaleAuthentication
from api.models import CloudAccount, Instance, MachineImage
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
    queryset = CloudAccount.objects.all()

    def get_queryset(self):
        """Get the queryset filtered to appropriate user."""
        user = self.request.user
        if not user.is_superuser:
            return self.queryset.filter(user=user)
        user_id = self.request.query_params.get("user_id", None)
        if user_id is not None:
            user_id = convert_param_to_int("user_id", user_id)
            return self.queryset.filter(user__id=user_id)
        return self.queryset


class InstanceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all or retrieve a single instance.

    Authenticate via 3scale.
    Do not allow to create, update, replace, or delete an instance at
    this view because we currently **only** allow instances to be retrieved.
    """

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.InstanceSerializer
    queryset = Instance.objects.all()

    def get_queryset(self):
        """Filter the queryset."""
        # Filter to the appropriate user
        user = self.request.user
        if not user.is_superuser:
            self.queryset = self.queryset.filter(cloud_account__user__id=user.id)
        user_id = self.request.query_params.get("user_id", None)
        if user_id is not None:
            user_id = convert_param_to_int("user_id", user_id)
            self.queryset = self.queryset.filter(cloud_account__user__id=user_id)

        # Filter based on the instance running
        running_since = self.request.query_params.get("running_since", None)
        if running_since is not None:
            running_since = parse(running_since)
            if not running_since.tzinfo:
                running_since = running_since.replace(tzinfo=tz.tzutc())

            self.queryset = (
                self.queryset.prefetch_related("run_set")
                .filter(run__start_time__isnull=False, run__end_time__isnull=True)
                .annotate(Max("run__start_time"))
                .filter(run__start_time__max__lte=running_since)
            )

        return self.queryset


class MachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List all, or retrieve a single machine image.

    Authenticate via 3scale.
    Do not allow to create, update, replace, or delete an machine image at
    this view.
    """

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.MachineImageSerializer
    queryset = MachineImage.objects.all()

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
            return (
                self.queryset.filter(instance__cloud_account__user_id=user.id)
                .order_by("id")
                .distinct()
            )
        user_id = self.request.query_params.get("user_id", None)
        if user_id is not None:
            user_id = convert_param_to_int("user_id", user_id)
            return (
                self.queryset.filter(instance__cloud_account__user_id=user_id)
                .order_by("id")
                .distinct()
            )
        return self.queryset.order_by("id")

    @action(detail=True, methods=["post"])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        user = self.request.user

        if not user.is_superuser:
            return Response(status=status.HTTP_403_FORBIDDEN)

        machine_image = self.get_object()
        machine_image.status = MachineImage.PENDING
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

    def list(self, *args, **kwargs):
        """Get cloud account ids currently used by this installation."""
        response = {
            "aws_account_id": _get_primary_account_id(),
            "aws_policies": {"traditional_inspection": cloudigrade_policy,},
            "version": settings.CLOUDIGRADE_VERSION,
        }
        return Response(response)


class DailyConcurrentUsageViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    """Generate report of concurrent usage within a time frame."""

    authentication_classes = (ThreeScaleAuthentication,)
    serializer_class = serializers.DailyConcurrentUsageSerializer

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
            user_id = self.request.query_params.get("user_id", None)
        if user_id is not None:
            try:
                user_id = convert_param_to_int("user_id", user_id)
            except exceptions.ValidationError as e:
                errors.update(e.detail)

        cloud_account_id = self.request.query_params.get("cloud_account_id", None)
        if cloud_account_id is not None:
            try:
                cloud_account_id = convert_param_to_int(
                    "cloud_account_id", cloud_account_id
                )
            except exceptions.ValidationError as e:
                errors.update(e.detail)

        if errors:
            raise exceptions.ValidationError(errors)

        queryset = DailyConcurrentUsageDummyQueryset(
            start_date, end_date, user_id, cloud_account_id
        )
        return queryset


@api_view(["POST"])
@schema(None)
def availability_check(request):
    """
    Attempt to re-enable cloudigrade accounts with matching source_id.

    This is an internal only API, so we do not want it to be in the openapi.spec.
    """
    data = request.data
    source_id = data.get("source_id")
    if not source_id:
        raise exceptions.ValidationError(detail="source_id field is required")

    cloudaccounts = CloudAccount.objects.filter(platform_source_id=source_id)
    for cloudaccount in cloudaccounts:
        cloudaccount.enable()

    return Response(status=status.HTTP_204_NO_CONTENT)
