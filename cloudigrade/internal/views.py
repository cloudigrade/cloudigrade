"""Internal views for cloudigrade API."""
import json
import logging
import os

from app_common_python import isClowderEnabled
from dateutil import tz
from dateutil.parser import parse
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.utils.translation import gettext as _
from rest_framework import exceptions, permissions, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    renderer_classes,
    schema,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from api import models, tasks
from api.tasks import enable_account
from api.util import find_problematic_runs
from internal import redis, serializers
from internal.authentication import (
    IdentityHeaderAuthenticationInternal,
)
from internal.renderers import JsonBytesRenderer
from util import exceptions as util_exceptions
from util.cache import get_cache_key_timeout
from util.misc import redact_json_dict_secrets
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
def delete_cloud_accounts_not_in_sources(request):
    """
    Delete cloud accounts that are not in sources.

    This internal api allows the user to manually trigger the periodic task
    delete_cloud_accounts_not_in_sources. This task deletes CloudAccounts and
    related *CloudAccount objects that do not have a related account in
    sources.
    """
    tasks.delete_cloud_accounts_not_in_sources.apply_async()

    return Response(status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def migrate_account_numbers_to_org_ids(request):
    """
    Trigger a migrate_account_numbers_to_org_id task function to run.

    This triggers a Celery task, `migrate_account_numbers_to_org_ids`
    Because the task runs asynchronously, a 202 response will be returned immediately
    even though the task may not actually have completed execution.

    Example request using httpie:

        http POST :8000/internal/migrate_account_numbers_to_org_ids/

    And the response for that example:

        HTTP/1.1 202 Accepted
    """
    logger.info(
        _("Internal API invoking the migrate_account_numbers_to_org_ids task"),
    )
    tasks.migrate_account_numbers_to_org_ids.apply_async()

    return Response(status=status.HTTP_202_ACCEPTED)


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

        http post :8000/internal/sources_kafka/ \
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
        func = tasks.update_from_sources_kafka_message

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


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def recalculate_runs(request):
    """
    Trigger a recalculate_runs_for_* task function to run.

    Optional POST params include "cloud_account_id" and "since".

    This triggers a Celery task, either `recalculate_runs_for_all_cloud_accounts` or
    `recalculate_runs_for_cloud_account_id` depending on if `cloud_account_id` is given.
    Because the task runs asynchronously, a 202 response will be returned immediately
    even though the task may not actually have completed execution.

    Example request using httpie:

        http :8000/internal/recalculate_runs/ \
            cloud_account_id="420" \
            since="2021-06-09"

    And the response for that example:

        HTTP/1.1 202 Accepted
    """
    data = request.data

    try:
        if cloud_account_id := data.get("cloud_account_id"):
            cloud_account_id = int(cloud_account_id)
    except (ValueError, TypeError) as e:
        raise exceptions.ValidationError({"cloud_account_id": e})

    try:
        if since := data.get("since"):
            # We need a datetime object, not just the input string.
            since = parse(since)
        if since and not since.tzinfo:
            # Force to UTC if no timezone/offset was provided.
            since = since.replace(tzinfo=tz.tzutc())
    except ValueError as e:
        raise exceptions.ValidationError({"since": e})

    if cloud_account_id:
        logger.info(
            _(
                "internal API calling recalculate_runs_for_cloud_account_id "
                "with args %(args)s"
            ),
            {"args": (cloud_account_id, since)},
        )
        tasks.recalculate_runs_for_cloud_account_id.apply_async(
            args=(cloud_account_id, since), serializer="pickle"
        )
    else:
        logger.info(
            _(
                "internal API calling recalculate_runs_for_all_cloud_accounts "
                "with args %(args)s"
            ),
            {"args": (since,)},
        )
        tasks.recalculate_runs_for_all_cloud_accounts.apply_async(
            args=(since,), serializer="pickle"
        )

    return Response(status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def recalculate_concurrent_usage(request):
    """
    Trigger a recalculate_concurrent_usage_for_* task function to run.

    Optional POST params include "user_id" and "since".

    This triggers a Celery task, either `recalculate_concurrent_usage_for_all_users` or
    `recalculate_concurrent_usage_for_user_id` depending on if `user_id` is given.
    Because the task runs asynchronously, a 202 response will be returned immediately
    even though the task may not actually have completed execution.

    Example request using httpie:

        http :8000/internal/recalculate_concurrent_usage/ \
            user_id="420" \
            since="2021-06-09"

    And the response for that example:

        HTTP/1.1 202 Accepted
    """
    data = request.data

    try:
        if user_id := data.get("user_id"):
            user_id = int(user_id)
    except (ValueError, TypeError) as e:
        raise exceptions.ValidationError({"user_id": e})

    try:
        if since := data.get("since"):
            # We need a date object, not just the input string.
            since = parse(since).date()
    except ValueError as e:
        raise exceptions.ValidationError({"since": e})

    if user_id:
        logger.info(
            _(
                "internal API calling recalculate_concurrent_usage_for_user_id "
                "with args %(args)s"
            ),
            {"args": (user_id, since)},
        )
        tasks.recalculate_concurrent_usage_for_user_id.apply_async(
            args=(user_id, since), serializer="pickle"
        )
    else:
        logger.info(
            _(
                "internal API calling recalculate_concurrent_usage_for_all_users "
                "with args %(args)s"
            ),
            {"args": (since,)},
        )
        tasks.recalculate_concurrent_usage_for_all_users.apply_async(
            args=(since,), serializer="pickle"
        )

    return Response(status=status.HTTP_202_ACCEPTED)


@api_view(["GET", "POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def cache_keys(request, key):
    """Post or Get Cloudigrade cache keys."""
    method = request.method.lower()
    if method == "get":
        """Get a single cache key."""
        value = cache.get(key)
        if value is None:
            raise Http404
        else:
            data = {
                "key": key,
                "value": value,
                "timeout": get_cache_key_timeout(key),
            }
            return Response(data=data)
    elif method == "post":
        """Post a single cache key."""
        value = request.data.get("value")
        if value is None:
            raise exceptions.ValidationError(detail="value field is required")
        timeout = request.data.get("timeout")

        logger.info(
            _("Setting Cache key='%(key)s', timeout=%(timeout)s"),
            {"key": key, "timeout": timeout},
        )
        if timeout:
            cache.set(key, value, timeout=int(timeout))
        else:
            cache.set(key, value)
        return Response(data=None)


@api_view(["GET"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@schema(None)
def get_cdappconfig_json(request):
    """Get the Clowder-provided cdappconfig.json for troubleshooting."""
    if not isClowderEnabled():
        raise Http404
    try:
        with open(os.environ.get("ACG_CONFIG")) as config_file:
            data = json.load(config_file)
    except FileNotFoundError:
        raise Http404
    except Exception as e:
        logger.exception(e)
        raise
    if settings.IS_PRODUCTION:
        redact_json_dict_secrets(data)
    return Response(data)


class ProblematicRunList(APIView):
    """List all problematic unending Runs or try to fix them."""

    authentication_classes = [IdentityHeaderAuthenticationInternal]
    permission_classes = [permissions.AllowAny]
    schema = None

    def get(self, request):
        """List all problematic unending Runs."""
        user_id = request.query_params.get("user_id")
        runs = find_problematic_runs(user_id)
        serializer = serializers.InternalRunSerializer(runs, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Attempt to fix all problematic unending Runs."""
        user_id = request.data.get("user_id")
        runs = find_problematic_runs(user_id)
        run_ids = [run.id for run in runs]
        if run_ids:
            logger.info(
                _("Preparing to fix problematic runs: %(run_ids)s"),
                {"run_ids": run_ids},
            )
            task_result = tasks.fix_problematic_runs.delay(run_ids)
            logger.info(
                _("fix_problematic_runs task is %(task)s"), {"task": task_result}
            )
        return Response(status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@authentication_classes([IdentityHeaderAuthenticationInternal])
@permission_classes([permissions.AllowAny])
@renderer_classes([JsonBytesRenderer])
@schema(None)
def redis_raw(request):
    """
    Perform raw commands against the underlying Redis cache.

    This is an internal only API, so we do not want it to be in the openapi.spec.
    """
    serializer = serializers.InternalRedisRawInputSerializer(data=request.data)
    if serializer.is_valid(raise_exception=True):
        command = serializer.validated_data["command"]
        args = serializer.validated_data.get("args", [])

        if command in serializer.destructive_commands:
            logger.warning(
                _(
                    "potentially destructive redis command via internal api: "
                    "%(command)s"
                ),
                {"command": command},
            )

        try:
            results = redis.execute_command(command, args)
        except TypeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({"results": results}, status=status.HTTP_200_OK)
