"""Internal views for cloudigrade API."""
import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django_filters import rest_framework as django_filters
from rest_framework import exceptions, mixins, permissions, status, viewsets
from rest_framework.decorators import (
    action,
    api_view,
    authentication_classes,
    permission_classes,
    schema,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from api import models, schemas, tasks
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.serializers import CloudAccountSerializer
from api.tasks import enable_account
from api.views import AccountViewSet, DailyConcurrentUsageViewSet
from internal import filters, serializers
from internal.authentication import (
    IdentityHeaderAuthenticationInternal,
    IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader,
    IdentityHeaderAuthenticationInternalCreateUser,
)
from internal.util import find_unending_runs_power_off_events
from util import exceptions as util_exceptions
from util.misc import get_today
from util.redhatcloud import identity

logger = logging.getLogger(__name__)


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
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

    cloudaccounts = models.CloudAccount.objects.filter(platform_source_id=source_id)
    for cloudaccount in cloudaccounts:
        logger.info(
            _(
                "Availability check for source ID %(source_id)s triggering task "
                "to enable cloud account %(cloudaccount)s"
            ),
            {"source_id": source_id, "cloudaccount": cloudaccount},
        )
        enable_account.delay(cloudaccount.id)

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def fake_error(request):
    """
    Cause an error for internal testing purposes.

    This view function allows us to exercise our log and exception handlers and to
    verify that the Sentry integration works as expected.

    request.data may contain "name" which should be the string name of an exception
    class in util.exceptions and "kwargs" which should be the keyword arguments for that
    named class. Raise that exception if inputs are valid, else raise ValidationError.

    Example request using httpie:

        http :8000/internal/error/ \
            name='ValidationError' kwargs:='{"detail":{"potato": "is precious"}}'

    And the response for that example:

        HTTP/1.1 400 Bad Request

        {
            "potato": "is precious"
        }
    """
    data = request.data
    name = data.get("name")
    kwargs = data.get("kwargs") or {}
    cls = None
    if name and hasattr(util_exceptions, name):
        cls = getattr(util_exceptions, name)
    if cls and Exception in cls.mro():
        logger.warning("Fake %(name)s(**%(kwargs)s)", {"name": name, "kwargs": kwargs})
        try:
            raise cls(**kwargs)
        except TypeError as e:
            logger.info(e)
    else:
        logger.warning("%(name)s is not an exception.", {"name": name})
    raise exceptions.ValidationError()


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def sources_kafka(request):
    """
    Handle an HTTP POST as if it was a Kafka message from sources-api.

    The POST data should have three attributes that represent the would-be extracted
    data from a Kafka message: value (dict), headers (list), and event_type (string).
    The value and headers attributes should be sent as JSON. For example, using httpie:

        http post :8000/internal/api/cloudigrade/v1/sources_kafka/ \
            event_type="ApplicationAuthentication.destroy" \
            value:='{"application_id": 100, "authentication_id":200, "id": 300}' \
            headers:='[["x-rh-identity","'"$(echo -n \
            '{"identity":{"account_number":"1701","user":{"is_org_admin":true}}}' \
            | base64)"'"]]'
    """
    data = request.data
    event_type = data.get("event_type")
    value = data.get("value")
    headers = data.get("headers")

    if not identity.get_x_rh_identity_header(headers):
        raise exceptions.ValidationError(
            {"headers": _("headers is not valid base64 encoded json")}
        )

    func = None
    if event_type == "ApplicationAuthentication.create":
        func = tasks.create_from_sources_kafka_message
    elif event_type == "ApplicationAuthentication.destroy":
        func = tasks.delete_from_sources_kafka_message
    elif event_type == "Authentication.update":
        func = tasks.update_from_source_kafka_message

    if func:
        func(value, headers)

    response = {
        "request": {
            "event_type": event_type,
            "value": value,
            "headers": headers,
        },
        "function": func.__name__ if func is not None else None,
    }

    return JsonResponse(data=response)


class ProblematicUnendingRunList(APIView):
    """List all problematic unending Runs or try to fix them."""

    authentication_classes = [IdentityHeaderAuthenticationInternal]
    permission_classes = [permissions.AllowAny]
    schema = None

    def get(self, request):
        """List all problematic unending Runs."""
        user_id = request.query_params.get("user_id")
        run_events = find_unending_runs_power_off_events(user_id)
        runs = [run for run, event in run_events]
        serializer = serializers.InternalRunSerializer(runs, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Attempt to fix all problematic unending Runs."""
        user_id = request.data.get("user_id")
        run_events = find_unending_runs_power_off_events(user_id)
        for run, event in run_events:
            task_result = tasks.process_instance_event.delay(event)
            logger.warning(
                _(
                    "Attempting to fix problematic %(run)s with %(event)s "
                    "in task %(task_result)s"
                ),
                {"run": run, "event": event, "task_result": task_result},
            )
        return Response(status=status.HTTP_202_ACCEPTED)


class InternalViewSetMixin:
    """Mixin of common attributes for our internal ViewSet classes."""

    authentication_classes = [IdentityHeaderAuthenticationInternal]
    permission_classes = [permissions.AllowAny]
    filter_backends = [django_filters.DjangoFilterBackend]


class InternalAccountViewSet(
    InternalViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    AccountViewSet,
):
    """
    Create, retrieve, update, delete, or list AwsCloudAccounts for internal use.

    Unlike most of our other internal ViewSets, this one extends our existing public
    AccountViewSet in order to move our "legacy" writable API for accounts out of the
    public space and into the internal space.

    This ViewSet uses custom permission and authentication handling to force only the
    "create" action (from HTTP POST) to have a proper User from the identity header. We
    need that authenticated User in order to create the CloudAccount object.
    """

    queryset = models.CloudAccount.objects.all()
    schema = schemas.DescriptiveAutoSchema(
        "cloud account",
        custom_responses={"DELETE": {"202": {"description": ""}}},
        operation_id_base="Account",
    )
    serializer_class = CloudAccountSerializer

    def get_permissions(self):
        """Instantiate and return the list of permissions that this view requires."""
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = self.permission_classes
        return [permission() for permission in permission_classes]

    def get_authenticators(self):
        """Instantiate and return the list of authenticators that this view can use."""
        # Note: We can't use .action like get_permissions because get_authenticators is
        # called from initialize_request *before* .action is set on the request object.
        if self.request.method.lower() == "post":
            authentication_classes = [IdentityHeaderAuthenticationInternalCreateUser]
        else:
            authentication_classes = self.authentication_classes
        return [auth() for auth in authentication_classes]

    def destroy(self, request, *args, **kwargs):
        """Destroy the CloudAccount but return 202 instead of 204."""
        response = super(InternalAccountViewSet, self).destroy(request, *args, **kwargs)
        if response.status_code == status.HTTP_204_NO_CONTENT:
            response = Response(
                data=response.data,
                status=status.HTTP_202_ACCEPTED,
                template_name=response.template_name,
                content_type=response.content_type,
            )
        return response

    def perform_destroy(self, instance):
        """Delay an async task to destroy the instance."""
        tasks.delete_cloud_account.delay(instance.id)


class InternalUserViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Users for internal use."""

    queryset = User.objects.all()
    serializer_class = serializers.InternalUserSerializer
    filterset_fields = {
        "username": ["exact"],
        "date_joined": ["lt", "exact", "gt"],
    }


class InternalUserTaskLockViewSet(
    InternalViewSetMixin,
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    """Retrieve, delete, or list UserTaskLocks for internal use."""

    queryset = models.UserTaskLock.objects.all()
    serializer_class = serializers.InternalUserTaskLockSerializer
    filterset_fields = {
        "user": ["exact"],
        "locked": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalCloudAccountViewSet(
    InternalViewSetMixin, mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve, delete, or list CloudAccounts for internal use."""

    queryset = models.CloudAccount.objects.all()
    serializer_class = serializers.InternalCloudAccountSerializer
    filterset_class = filters.InternalCloudAccountFilterSet


class InternalInstanceViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Instances for internal use."""

    queryset = models.Instance.objects.all()
    serializer_class = serializers.InternalInstanceSerializer
    filterset_class = filters.InternalInstanceFilterSet


class InternalInstanceEventViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list InstanceEvents for internal use."""

    queryset = models.InstanceEvent.objects.all()
    serializer_class = serializers.InternalInstanceEventSerializer
    filterset_class = filters.InternalInstanceEventFilterSet


class InternalMachineImageViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve, reinspect, or list MachineImages for internal use."""

    queryset = models.MachineImage.objects.all()
    serializer_class = serializers.InternalMachineImageSerializer
    filterset_fields = {
        "architecture": ["exact"],
        "object_id": ["exact"],
        "name": ["exact"],
        "status": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }

    @action(detail=True, methods=["post"])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        machine_image = self.get_object()
        machine_image.status = models.MachineImage.PENDING
        machine_image.save()

        serializer = serializers.InternalMachineImageSerializer(
            machine_image, context={"request": request}
        )

        return Response(serializer.data)


class InternalRunViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list Runs for internal use."""

    queryset = models.Run.objects.all()
    serializer_class = serializers.InternalRunSerializer
    filterset_class = filters.InternalRunFilterSet


class InternalMachineImageInspectionStartViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list MachineImageInspectionStarts for internal use."""

    queryset = models.MachineImageInspectionStart.objects.all()
    serializer_class = serializers.InternalMachineImageInspectionStartSerializer
    filterset_fields = {
        "machineimage": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalConcurrentUsageViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.ConcurrentUsage.objects.all()
    serializer_class = serializers.InternalConcurrentUsageSerializer
    filterset_class = filters.InternalConcurrentUsageFilterSet


class InternalConcurrentUsageCalculationTaskViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsageCalculationTasks for internal use."""

    queryset = models.ConcurrentUsageCalculationTask.objects.all()
    serializer_class = serializers.InternalConcurrentUsageCalculationTaskSerializer
    filterset_fields = {
        "status": ["exact"],
        "user": ["exact"],
        "task_id": ["exact"],
        "date": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalInstanceDefinitionViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list ConcurrentUsages for internal use."""

    queryset = models.InstanceDefinition.objects.all()
    serializer_class = serializers.InternalInstanceDefinitionSerializer
    filterset_fields = {
        "cloud_type": ["exact"],
        "instance_type": ["exact"],
        "memory": ["exact"],
        "vcpu": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsCloudAccountViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsCloudAccount for internal use."""

    queryset = aws_models.AwsCloudAccount.objects.all()
    serializer_class = serializers.InternalAwsCloudAccountSerializer
    filterset_class = filters.InternalAwsCloudAccountFilterSet


class InternalAwsInstanceViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AwsInstances for internal use."""

    queryset = aws_models.AwsInstance.objects.all()
    serializer_class = serializers.InternalAwsInstanceSerializer
    filterset_fields = {
        "ec2_instance_id": ["exact"],
        "region": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsInstanceEventViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsInstanceEvents for internal use."""

    queryset = aws_models.AwsInstanceEvent.objects.all()
    serializer_class = serializers.InternalAwsInstanceEventSerializer
    filterset_fields = {
        "subnet": ["exact"],
        "instance_type": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsMachineImageViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsMachineImages for internal use."""

    queryset = aws_models.AwsMachineImage.objects.all()
    serializer_class = serializers.InternalAwsMachineImageSerializer
    filterset_fields = {
        "ec2_ami_id": ["exact"],
        "platform": ["exact"],
        "owner_aws_account_id": ["exact"],
        "region": ["exact"],
        "aws_marketplace_image": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAwsMachineImageCopyViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AwsMachineImageCopies for internal use."""

    queryset = aws_models.AwsMachineImageCopy.objects.all()
    serializer_class = serializers.InternalAwsMachineImageCopySerializer
    filterset_fields = {
        "reference_awsmachineimage": ["exact"],
        "ec2_ami_id": ["exact"],
        "platform": ["exact"],
        "owner_aws_account_id": ["exact"],
        "region": ["exact"],
        "aws_marketplace_image": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAzureCloudAccountViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureCloudAccount.objects.all()
    serializer_class = serializers.InternalAzureCloudAccountSerializer
    filterset_class = filters.InternalAzureCloudAccountFilterSet


class InternalAzureInstanceViewSet(InternalViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Retrieve or list AzureInstanceEvents for internal use."""

    queryset = azure_models.AzureInstance.objects.all()
    serializer_class = serializers.InternalAzureInstanceSerializer
    filterset_fields = {
        "region": ["exact"],
        "resource_id": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAzureInstanceEventViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureInstanceEvents for internal use."""

    queryset = azure_models.AzureInstanceEvent.objects.all()
    serializer_class = serializers.InternalAzureInstanceEventSerializer
    filterset_fields = {
        "instance_type": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


class InternalAzureMachineImageViewSet(
    InternalViewSetMixin, viewsets.ReadOnlyModelViewSet
):
    """Retrieve or list AzureMachineImages for internal use."""

    queryset = azure_models.AzureMachineImage.objects.all()
    serializer_class = serializers.InternalAzureMachineImageSerializer
    filterset_fields = {
        "azure_marketplace_image": ["exact"],
        "region": ["exact"],
        "resource_id": ["exact"],
        "created_at": ["lt", "exact", "gt"],
        "updated_at": ["lt", "exact", "gt"],
    }


@method_decorator(transaction.non_atomic_requests, name="dispatch")
class InternalDailyConcurrentUsageViewSet(DailyConcurrentUsageViewSet):
    """
    Generate report of concurrent usage within a time frame.

    This viewset has to be wrapped in a non_atomic_requests decorator. DRF by default
    runs viewset methods inside of an atomic transaction. But in this case we have to
    create ConcurrentUsageCalculationTask to schedule jobs even when we raise a
    ResultsUnavailable 425 exception.
    """

    def get_authenticators(self):
        """Instantiate and return the list of authenticators that this view can use."""
        authentication_classes = [
            IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader
        ]
        return [auth() for auth in authentication_classes]

    def latest_start_date(self):
        """Return the latest allowed start_date."""
        return get_today()

    def latest_end_date(self):
        """Return the latest allowed end_date."""
        return get_today() + timedelta(days=1)

    def late_start_date_error(self):
        """Return the error message for specifying a late start_date."""
        return _("start_date cannot be in the future.")
