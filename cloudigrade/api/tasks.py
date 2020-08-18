"""
Celery tasks for use in the api v2 app.

Note for developers:
If you find yourself adding a new Celery task, please be aware of how Celery
determines which queue to read and write to work on that task. By default,
Celery tasks will go to a queue named "celery". If you wish to separate a task
onto a different queue (which may make it easier to see the volume of specific
waiting tasks), please be sure to update all the relevant configurations to
use that custom queue. This includes CELERY_TASK_ROUTES in config and the
Celery worker's --queues argument (see deployment-configs.yaml in shiftigrade).
"""
import json
import logging
from datetime import timedelta

from celery import shared_task
from dateutil import parser as date_parser
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from requests.exceptions import BaseHTTPError, RequestException

from api import error_codes
from api.clouds.aws.tasks import (
    CLOUD_KEY,
    CLOUD_TYPE_AWS,
    configure_customer_aws_and_create_cloud_account,
    scale_down_cluster,
)
from api.clouds.aws.util import (
    persist_aws_inspection_cluster_results,
    start_image_inspection,
    update_aws_cloud_account,
)
from api.models import (
    CloudAccount,
    ConcurrentUsageCalculationTask,
    Instance,
    InstanceEvent,
    MachineImage,
    Run,
)
from api.util import (
    calculate_max_concurrent_usage,
    calculate_max_concurrent_usage_from_runs,
    normalize_runs,
    recalculate_runs,
)
from util import aws, insights
from util.celery import retriable_shared_task
from util.misc import get_now

logger = logging.getLogger(__name__)


@retriable_shared_task(autoretry_for=(RequestException, BaseHTTPError))
def create_from_sources_kafka_message(message, headers):  # noqa: C901
    """
    Create our model objects from the Sources Kafka message.

    Because the Sources API may not always be available, this task must
    gracefully retry if communication with Sources fails unexpectedly.

    If this function succeeds, it spawns another async task to set up the
    customer's AWS account (configure_customer_aws_and_create_cloud_account).

    Args:
        message (dict): the "value" attribute of a message from a Kafka
            topic generated by the Sources service and having event type
            "ApplicationAuthentication.create"
        headers (list): the headers of a message from a Kafka topic
            generated by the Sources service and having event type
            "ApplicationAuthentication.create"

    """
    authentication_id = message.get("authentication_id", None)
    application_id = message.get("application_id", None)
    account_number, platform_id = insights.extract_ids_from_kafka_message(
        message, headers
    )

    if account_number is None or authentication_id is None or application_id is None:
        logger.error(_("Aborting creation. Incorrect message details."))
        return

    application = insights.get_sources_application(account_number, application_id)
    if not application:
        logger.info(
            _(
                "Application ID %(application_id)s for account number "
                "%(account_number)s does not exist; aborting cloud account creation."
            ),
            {"application_id": application_id, "account_number": account_number},
        )
        return

    application_type = application["application_type_id"]
    if application_type is not insights.get_sources_cloudigrade_application_type_id(
        account_number
    ):
        logger.info(_("Aborting creation. Application Type is not cloudmeter."))
        return

    authentication = insights.get_sources_authentication(
        account_number, authentication_id
    )
    if not authentication:
        error_code = error_codes.CG2000
        error_code.log_internal_message(
            logger,
            {"authentication_id": authentication_id, "account_number": account_number},
        )
        error_code.notify(account_number, application_id)
        return

    authtype = authentication.get("authtype")
    if authtype not in settings.SOURCES_CLOUDMETER_AUTHTYPES:
        error_code = error_codes.CG2001
        error_code.log_internal_message(
            logger, {"authentication_id": authentication_id, "authtype": authtype}
        )
        error_code.notify(account_number, application_id)
        return

    resource_type = authentication.get("resource_type")
    endpoint_id = authentication.get("resource_id")

    if resource_type != settings.SOURCES_ENDPOINT_TYPE:
        error_code = error_codes.CG2002
        error_code.log_internal_message(
            logger, {"endpoint_id": endpoint_id, "account_number": account_number}
        )
        error_code.notify(account_number, application_id)
        return

    endpoint = insights.get_sources_endpoint(account_number, endpoint_id)
    if not endpoint:
        error_code = error_codes.CG2003
        error_code.log_internal_message(
            logger, {"endpoint_id": endpoint_id, "account_number": account_number}
        )
        error_code.notify(account_number, application_id)
        return

    source_id = endpoint.get("source_id")

    password = authentication.get("password")

    if not password:
        error_code = error_codes.CG2004
        error_code.log_internal_message(
            logger, {"authentication_id": authentication_id}
        )
        error_code.notify(account_number, application_id)
        return

    with transaction.atomic():
        user, created = User.objects.get_or_create(username=account_number)
        if created:
            user.set_unusable_password()
            logger.info(
                _("User %s was not found and has been created."), account_number,
            )

    # Conditionalize the logic for different cloud providers
    if authtype == settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE:
        configure_customer_aws_and_create_cloud_account.delay(
            user.username,
            password,
            authentication_id,
            application_id,
            endpoint_id,
            source_id,
        )


@retriable_shared_task(autoretry_for=(RuntimeError,))  # noqa: C901
@aws.rewrap_aws_errors
def delete_from_sources_kafka_message(message, headers, event_type):  # noqa: C901
    """
    Delete our cloud account as per the Sources Kafka message.

    This function is decorated to retry if an unhandled `RuntimeError` is
    raised, which is the exception we raise in `rewrap_aws_errors` if we
    encounter an unexpected error from AWS. This means it should keep retrying
    if AWS is misbehaving.

    Args:
        message (dict): a message from the Kafka topic generated by the
            Sources service and having event type "Authentication.destroy"
        headers (list): the headers of a message from a Kafka topic
            generated by the Sources service and having event type
            "Authentication.destroy", "Endpoint.destroy" or "Source.destroy"
        event_type (str): A string describing the type of destroy event.

    """
    account_number, platform_id = insights.extract_ids_from_kafka_message(
        message, headers
    )

    logger.info(
        _(
            "delete_from_sources_kafka_message for account_number %(account_number)s, "
            "platform_id %(platform_id)s, and event_type %(event_type)s"
        ),
        {
            "account_number": account_number,
            "platform_id": platform_id,
            "event_type": event_type,
        },
    )

    if account_number is None or platform_id is None:
        logger.error(_("Aborting deletion. Incorrect message details."))
        return

    filter = None
    if event_type == settings.SOURCE_DESTROY_EVENT:
        filter = Q(platform_source_id=platform_id)
    elif event_type == settings.ENDPOINT_DESTROY_EVENT:
        filter = Q(platform_endpoint_id=platform_id)
    elif event_type == settings.AUTHENTICATION_DESTROY_EVENT:
        filter = Q(platform_authentication_id=platform_id)
    elif event_type == settings.APPLICATION_DESTROY_EVENT:
        filter = Q(platform_application_id=platform_id)
    elif event_type == settings.APPLICATION_AUTHENTICATION_DESTROY_EVENT:
        authentication_id = message["authentication_id"]
        application_id = message["application_id"]
        filter = Q(
            platform_application_id=application_id,
            platform_authentication_id=authentication_id,
        )

    if not filter:
        logger.error(
            _("Not enough details to delete a CloudAccount from message: %s"), message
        )
        return

    with transaction.atomic():
        logger.info(_("Deleting CloudAccounts using filter %s"), filter)
        # IMPORTANT NOTES FOR FUTURE DEVELOPERS:
        #
        # This for loop and select_for_update may seem unnecessary, but they actually
        # serve a very important purpose. We use pre_delete Django signals with
        # CloudAccount, but that has the unfortunate side effect of Django *not* getting
        # a row-level lock in the DB for each CloudAccount we want to delete until
        # *after* all of the pre_delete logic completes. Why is that bad? If we receive
        # two requests in quick succession to delete the same CloudAccount but we don't
        # have it locked, the second request can get the CloudAccount and expect it to
        # be available while the first request is processing that CloudAccount's
        # pre_delete signal, and they can collide when making changes related to the
        # deletion.
        #
        # Using a for loop and select_for_update here means that we *immediately*
        # acquire each row-level lock *before* any signals fire, and that better
        # guarantees no two requests can attempt to delete the same CloudAccount
        # instance.
        #
        # Since select_for_update is a rather heavy-handed solution to this problem and
        # DB row-level locks can cause other in-transaction requests to hang waiting,
        # eventually we should consider refactoring away the pre_delete logic to avoid
        # possible resource contention issues and slowdowns.
        for cloud_account in CloudAccount.objects.select_for_update().filter(filter):
            cloud_account.delete()


@retriable_shared_task(autoretry_for=(RequestException, BaseHTTPError, RuntimeError))
@aws.rewrap_aws_errors
def update_from_source_kafka_message(message, headers):
    """
    Update our model objects from the Sources Kafka message.

    Because the Sources API may not always be available, this task must
    gracefully retry if communication with Sources fails unexpectedly.

    This function is also decorated to retry if an unhandled `RuntimeError` is
    raised, which is the exception we raise in `rewrap_aws_errors` if we
    encounter an unexpected error from AWS. This means it should keep retrying
    if AWS is misbehaving.

    Args:
        message (dict): the "value" attribute of a message from a Kafka
            topic generated by the Sources service and having event type
            "Authentication.update"
        headers (list): the headers of a message from a Kafka topic
            generated by the Sources service and having event type
            "Authentication.update"

    """
    account_number, authentication_id = insights.extract_ids_from_kafka_message(
        message, headers
    )

    if account_number is None or authentication_id is None:
        logger.error(_("Aborting update. Incorrect message details."))
        return

    try:
        clount = CloudAccount.objects.get(platform_authentication_id=authentication_id)

        authentication = insights.get_sources_authentication(
            account_number, authentication_id
        )

        if not authentication:
            logger.info(
                _(
                    "Authentication ID %(authentication_id)s for account number "
                    "%(account_number)s does not exist; aborting cloud account update."
                ),
                {
                    "authentication_id": authentication_id,
                    "account_number": account_number,
                },
            )
            return

        resource_type = authentication.get("resource_type")
        endpoint_id = authentication.get("resource_id")
        if resource_type != settings.SOURCES_ENDPOINT_TYPE:
            logger.info(
                _(
                    "Resource ID %(endpoint_id)s for account number %(account_number)s "
                    "is not of type Endpoint; aborting cloud account update."
                ),
                {"endpoint_id": endpoint_id, "account_number": account_number},
            )
            return

        endpoint = insights.get_sources_endpoint(account_number, endpoint_id)
        if not endpoint:
            logger.info(
                _(
                    "Endpoint ID %(endpoint_id)s for account number "
                    "%(account_number)s does not exist; aborting cloud account update."
                ),
                {"endpoint_id": endpoint_id, "account_number": account_number},
            )
            return

        source_id = endpoint.get("source_id")

        # If the Authentication being updated is arn, do arn things.
        # The kafka message does not always include authtype, so we get this from
        # the sources API call
        if authentication.get("authtype") == settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE:
            update_aws_cloud_account(
                clount,
                authentication.get("password"),
                account_number,
                authentication_id,
                endpoint_id,
                source_id,
            )
    except CloudAccount.DoesNotExist:
        # Is this authentication meant to be for us? We should check.
        # Get list of all app-auth objects and filter by our authentication
        response_json = insights.list_sources_application_authentications(
            account_number, authentication_id
        )

        if response_json.get("meta").get("count") > 0:
            for application_authentication in response_json.get("data"):
                create_from_sources_kafka_message.delay(
                    application_authentication, headers
                )
        else:
            logger.info(
                _(
                    "The updated authentication with ID %s and account number %s "
                    "is not managed by cloud meter."
                ),
                authentication_id,
                account_number,
            )


@shared_task
@transaction.atomic
def process_instance_event(event):
    """
    Process instance events that have been saved during log analysis.

    Note:
        When processing power_on type events, this triggers a recalculation of
        ConcurrentUsage objects. If the event is at some point in the
        not-too-recent past, this may take a while as every day since the event
        will get recalculated and saved. We do not anticipate this being a real
        problem in practice, but this has the potential to slow down unit test
        execution over time since their occurred_at values are often static and
        will recede father into the past from "today", resulting in more days
        needing to recalculate. This effect could be mitigated in tests by
        patching parts of the datetime module that are used to find "today".
    """
    after_run = Q(start_time__gt=event.occurred_at)
    during_run = Q(start_time__lte=event.occurred_at, end_time__gt=event.occurred_at)
    during_run_no_end = Q(start_time__lte=event.occurred_at, end_time=None)

    filters = after_run | during_run | during_run_no_end
    instance = Instance.objects.get(id=event.instance_id)

    if Run.objects.filter(filters, instance=instance).exists():
        recalculate_runs(event)
    elif event.event_type == InstanceEvent.TYPE.power_on:
        normalized_runs = normalize_runs([event])
        runs = []
        for index, normalized_run in enumerate(normalized_runs):
            logger.info(
                "Processing run {} of {}".format(index + 1, len(normalized_runs))
            )
            run = Run(
                start_time=normalized_run.start_time,
                end_time=normalized_run.end_time,
                machineimage_id=normalized_run.image_id,
                instance_id=normalized_run.instance_id,
                instance_type=normalized_run.instance_type,
                memory=normalized_run.instance_memory,
                vcpu=normalized_run.instance_vcpu,
            )
            run.save()
            runs.append(run)
        calculate_max_concurrent_usage_from_runs(runs)


@shared_task
@aws.rewrap_aws_errors
def persist_inspection_cluster_results_task():
    """
    Task to run periodically and read houndigrade messages.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    queue_url = aws.get_sqs_queue_url(settings.HOUNDIGRADE_RESULTS_QUEUE_NAME)
    successes, failures = [], []
    for message in aws.yield_messages_from_queue(
        queue_url, settings.AWS_SQS_MAX_HOUNDI_YIELD_COUNT
    ):
        logger.info(_('Processing inspection results with id "%s"'), message.message_id)

        inspection_results = json.loads(message.body)
        if inspection_results.get(CLOUD_KEY) == CLOUD_TYPE_AWS:
            try:
                persist_aws_inspection_cluster_results(inspection_results)
            except Exception as e:
                logger.exception(_("Unexpected error in result processing: %s"), e)
                logger.debug(_("Failed message body is: %s"), message.body)
                failures.append(message)
                continue

            logger.info(
                _("Successfully processed message id %s; deleting from queue."),
                message.message_id,
            )
            aws.delete_messages_from_queue(queue_url, [message])
            successes.append(message)
        else:
            logger.error(
                _('Unsupported cloud type: "%s"'), inspection_results.get(CLOUD_KEY)
            )
            failures.append(message)

    if successes or failures:
        scale_down_cluster.delay()
    else:
        logger.info("No inspection results found.")

    return successes, failures


@shared_task
@transaction.atomic
def inspect_pending_images():
    """
    (Re)start inspection of images in PENDING, PREPARING, or INSPECTING status.

    This generally should not be necessary for most images, but if an image
    inspection fails to proceed normally, this function will attempt to run it
    through inspection again.

    This function runs atomically in a transaction to protect against the risk
    of it being called multiple times simultaneously which could result in the
    same image being found and getting multiple inspection tasks.
    """
    updated_since = get_now() - timedelta(
        seconds=settings.INSPECT_PENDING_IMAGES_MIN_AGE
    )
    restartable_statuses = [
        MachineImage.PENDING,
        MachineImage.PREPARING,
        MachineImage.INSPECTING,
    ]
    images = MachineImage.objects.filter(
        status__in=restartable_statuses,
        instance__aws_instance__region__isnull=False,
        updated_at__lt=updated_since,
    ).distinct()
    logger.info(
        _(
            "Found %(number)s images for inspection that have not updated "
            "since %(updated_time)s"
        ),
        {"number": images.count(), "updated_time": updated_since},
    )

    for image in images:
        instance = image.instance_set.filter(aws_instance__region__isnull=False).first()
        arn = instance.cloud_account.content_object.account_arn
        ami_id = image.content_object.ec2_ami_id
        region = instance.content_object.region
        start_image_inspection(arn, ami_id, region)


@shared_task(bind=True, default_retry_delay=settings.CONCURRENT_USAGE_CALCULATION_DELAY)
def calculate_max_concurrent_usage_task(self, date, user_id):
    """
    Schedule a task to calculate maximum concurrent usage of RHEL instances.

    Args:
        date (str): the day during which we are measuring usage.
            Celery serializes the date as a string in the format "%Y-%B-%dT%H:%M:%S.
        user_id (int): required filter on user

    Returns:
        ConcurrentUsage for the given date and user ID.

    """
    # If the user does not exist, all the related ConcurrentUsage
    # objects should also have been removed, so we can exit early.
    if not User.objects.filter(id=user_id).exists():
        return

    date = date_parser.parse(date).date()

    # If there is already an calculate_max_concurrent_usage running for given
    # user and date, then retry this task later.
    if ConcurrentUsageCalculationTask.objects.filter(
        date=date, user__id=user_id, status=ConcurrentUsageCalculationTask.RUNNING
    ):
        logger.info(
            "calculate_max_concurrent_usage_task for user_id %(user_id)s "
            "and date %(date)s is already running. The current task will "
            "be retried later.",
            {"user_id": user_id, "date": date},
        )
        self.retry()

    logger.info(
        "Running calculate_max_concurrent_usage_task for user_id %(user_id)s "
        "and date %(date)s.",
        {"user_id": user_id, "date": date},
    )
    # Set task to running
    task_id = self.request.id
    calculation_task = ConcurrentUsageCalculationTask.objects.get(task_id=task_id)
    calculation_task.status = ConcurrentUsageCalculationTask.RUNNING
    calculation_task.save()

    try:
        calculate_max_concurrent_usage(date, user_id)
    except Exception:
        calculation_task.status = ConcurrentUsageCalculationTask.ERROR
        calculation_task.save()
        raise

    calculation_task.status = ConcurrentUsageCalculationTask.COMPLETE
    calculation_task.save()
    logger.info(
        "Completed calculate_max_concurrent_usage_task for user_id %(user_id)s "
        "and date %(date)s.",
        {"user_id": user_id, "date": date},
    )
