"""Tasks for various sources-api operations."""

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from requests.exceptions import BaseHTTPError, RequestException

from api import error_codes
from api.authentication import get_or_create_user
from api.clouds.aws.tasks import configure_customer_aws_and_create_cloud_account
from api.clouds.aws.util import update_aws_cloud_account
from api.clouds.azure.tasks import check_azure_subscription_and_create_cloud_account
from api.models import CloudAccount
from api.tasks.maintenance import _delete_cloud_accounts
from util import aws
from util.celery import retriable_shared_task
from util.exceptions import AwsThrottlingException, KafkaProducerException
from util.misc import lock_task_for_user_ids
from util.redhatcloud import sources

logger = logging.getLogger(__name__)


@retriable_shared_task(
    autoretry_for=(RequestException, BaseHTTPError, AwsThrottlingException),
    name="api.tasks.create_from_sources_kafka_message",
)
@aws.rewrap_aws_errors
def create_from_sources_kafka_message(message, headers):
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
    (
        account_number,
        org_id,
        platform_id,
    ) = sources.extract_ids_from_kafka_message(message, headers)

    if (
        (not account_number and not org_id)
        or authentication_id is None
        or application_id is None
    ):
        logger.error(_("Aborting creation. Incorrect message details."))
        return

    application, authentication = _get_and_verify_sources_data(
        account_number, org_id, application_id, authentication_id
    )
    if application is None or authentication is None:
        return

    authtype = authentication.get("authtype")
    if authtype not in settings.SOURCES_CLOUDMETER_AUTHTYPES:
        error_code = error_codes.CG2001
        error_code.log_internal_message(
            logger, {"authentication_id": authentication_id, "authtype": authtype}
        )
        error_code.notify(account_number, org_id, application_id)
        return

    resource_type = authentication.get("resource_type")
    resource_id = authentication.get("resource_id")
    if resource_type != settings.SOURCES_RESOURCE_TYPE:
        error_code = error_codes.CG2002
        error_code.log_internal_message(
            logger, {"resource_id": resource_id, "account_number": account_number}
        )
        error_code.notify(account_number, org_id, application_id)
        return

    source_id = application.get("source_id")
    authentication_token = authentication.get("username") or authentication.get(
        "password"
    )

    if not authentication_token:
        error_code = error_codes.CG2004
        error_code.log_internal_message(
            logger, {"authentication_id": authentication_id}
        )
        error_code.notify(account_number, org_id, application_id)
        return

    user = get_or_create_user(account_number, org_id)

    # Conditionalize the cloud account creation logic for different cloud providers.
    create_cloud_account_task = None

    if authtype == settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE:
        create_cloud_account_task = configure_customer_aws_and_create_cloud_account
    elif authtype == settings.SOURCES_CLOUDMETER_LIGHTHOUSE_AUTHTYPE:
        create_cloud_account_task = check_azure_subscription_and_create_cloud_account

    extras = authentication.get("extra", None)

    if create_cloud_account_task:
        transaction.on_commit(
            lambda: create_cloud_account_task.delay(
                user.account_number,
                user.org_id,
                authentication_token,
                authentication_id,
                application_id,
                source_id,
                extras,
            )
        )


def _get_and_verify_sources_data(
    account_number, org_id, application_id, authentication_id
):
    """
    Call the sources API and look up the object IDs we were given.

    Args:
        account_number (str): User account number.
        application_id (int): The application object id.
        authentication_id (int): the authentication object id.

    Returns:
        (dict, dict): application and authentication dicts if present and valid,
            otherwise None.
    """
    application = sources.get_application(account_number, org_id, application_id)
    if not application:
        logger.info(
            _(
                "Application ID %(application_id)s for account number "
                "%(account_number)s does not exist; aborting cloud account creation."
            ),
            {"application_id": application_id, "account_number": account_number},
        )
        return None, None

    application_type = application["application_type_id"]
    if application_type is not sources.get_cloudigrade_application_type_id(
        account_number, org_id
    ):
        logger.info(_("Aborting creation. Application Type is not cloudmeter."))
        return None, None

    authentication = sources.get_authentication(
        account_number, org_id, authentication_id
    )
    if not authentication:
        error_code = error_codes.CG2000
        error_code.log_internal_message(
            logger,
            {"authentication_id": authentication_id, "account_number": account_number},
        )
        error_code.notify(account_number, org_id, application_id)
        return application, None
    return application, authentication


@retriable_shared_task(
    autoretry_for=(RuntimeError, AwsThrottlingException),
    name="api.tasks.delete_from_sources_kafka_message",
)
@aws.rewrap_aws_errors
def delete_from_sources_kafka_message(message, headers):
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
            "Authentication.destroy" or "Source.destroy"

    """
    (
        account_number,
        org_id,
        platform_id,
    ) = sources.extract_ids_from_kafka_message(message, headers)

    logger.info(
        _(
            "delete_from_sources_kafka_message for account_number %(account_number)s, "
            "org_id %(org_id)s, "
            "platform_id %(platform_id)s"
        ),
        {
            "account_number": account_number,
            "org_id": org_id,
            "platform_id": platform_id,
        },
    )

    if (not account_number and not org_id) or platform_id is None:
        logger.error(_("Aborting deletion. Incorrect message details."))
        return

    authentication_id = message["authentication_id"]
    application_id = message["application_id"]
    query_filter = Q(
        platform_application_id=application_id,
        platform_authentication_id=authentication_id,
    )

    logger.info(_("Deleting CloudAccounts using filter %s"), query_filter)
    cloud_accounts = CloudAccount.objects.filter(query_filter)
    _delete_cloud_accounts(cloud_accounts)


@retriable_shared_task(
    autoretry_for=(
        RequestException,
        BaseHTTPError,
        RuntimeError,
        AwsThrottlingException,
    ),
    name="api.tasks.update_from_sources_kafka_message",
)
@aws.rewrap_aws_errors
def update_from_sources_kafka_message(message, headers):
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
    (
        account_number,
        org_id,
        authentication_id,
    ) = sources.extract_ids_from_kafka_message(message, headers)

    if (not account_number and not org_id) or authentication_id is None:
        logger.error(_("Aborting update. Incorrect message details."))
        return

    try:
        cloud_account = CloudAccount.objects.get(
            platform_authentication_id=authentication_id
        )

        authentication = sources.get_authentication(
            account_number, org_id, authentication_id
        )

        if not authentication:
            logger.info(
                _(
                    "Authentication ID %(authentication_id)s for "
                    "account number '%(account_number)s' or org_id '%(org_id)s' "
                    "does not exist; aborting cloud account update."
                ),
                {
                    "authentication_id": authentication_id,
                    "account_number": account_number,
                    "org_id": org_id,
                },
            )
            return

        resource_type = authentication.get("resource_type")
        application_id = authentication.get("resource_id")
        if resource_type != settings.SOURCES_RESOURCE_TYPE:
            logger.info(
                _(
                    "Resource ID %(resource_id)s for "
                    "account number '%(account_number)s' or org_id '%(org_id)s' "
                    "is not of type Application; aborting cloud account update."
                ),
                {
                    "resource_id": application_id,
                    "account_number": account_number,
                    "org_id": org_id,
                },
            )
            return

        application = sources.get_application(account_number, org_id, application_id)
        source_id = application.get("source_id")

        arn = authentication.get("username") or authentication.get("password")
        if not arn:
            logger.info(_("Could not update CloudAccount with no ARN provided."))
            error_code = error_codes.CG2004
            error_code.log_internal_message(
                logger, {"authentication_id": authentication_id}
            )
            error_code.notify(account_number, org_id, application_id)
            return

        # If the Authentication being updated is arn, do arn things.
        # The kafka message does not always include authtype, so we get this from
        # the sources API call
        if authentication.get("authtype") == settings.SOURCES_CLOUDMETER_ARN_AUTHTYPE:
            update_aws_cloud_account(
                cloud_account,
                arn,
                account_number,
                org_id,
                authentication_id,
                source_id,
            )
    except CloudAccount.DoesNotExist:
        # Is this authentication meant to be for us? We should check.
        # Get list of all app-auth objects and filter by our authentication
        response_json = sources.list_application_authentications(
            account_number, org_id, authentication_id
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


@retriable_shared_task(
    autoretry_for=(
        RequestException,
        BaseHTTPError,
        RuntimeError,
        AwsThrottlingException,
    ),
    name="api.tasks.pause_from_sources_kafka_message",
)
@aws.rewrap_aws_errors
def pause_from_sources_kafka_message(message, headers):
    """
    Pause processing a CloudAccount based on the given Sources Kafka message.

    Args:
        message (dict): the "value" attribute of a message from a Kafka
            topic generated by the Sources service and having event type
            "Application.pause"
        headers (list): the headers of a message from a Kafka topic
            generated by the Sources service and having event type
            "Application.pause"
    """
    (
        account_number,
        org_id,
        application_id,
    ) = sources.extract_ids_from_kafka_message(message, headers)

    if (account_number is None and org_id is None) or application_id is None:
        logger.error(
            _(
                "Aborting pause. Incorrect message details. "
                "account_number=%(account_number)s org_id=%(org_id) "
                "application_id=%(application_id)s"
            ),
            {
                "account_number": account_number,
                "org_id": org_id,
                "application_id": application_id,
            },
        )
        return

    try:
        cloud_account = CloudAccount.objects.get(platform_application_id=application_id)
        with lock_task_for_user_ids([cloud_account.user.id]):
            cloud_account.platform_application_is_paused = True
            cloud_account.save()
            # We do not want to notify sources when we disable here because it may
            # actually still be available. Since "paused" and "unavailable" are
            # orthogonal states, we should not act as though pausing also means making
            # unavailable. Only the periodic availability checks should be determining
            # that and updating sources if necessary.
            cloud_account.disable(notify_sources=False)
    except CloudAccount.DoesNotExist:
        logger.info(
            _(
                "CloudAccount for application ID %(application_id)s cannot pause "
                "because it does not exist"
            ),
            {"application_id": application_id},
        )


@retriable_shared_task(
    autoretry_for=(
        RequestException,
        BaseHTTPError,
        RuntimeError,
        AwsThrottlingException,
    ),
    name="api.tasks.unpause_from_sources_kafka_message",
)
@aws.rewrap_aws_errors
def unpause_from_sources_kafka_message(message, headers):
    """
    Unpause processing a CloudAccount based on the given Sources Kafka message.

    Args:
        message (dict): the "value" attribute of a message from a Kafka
            topic generated by the Sources service and having event type
            "Application.unpause"
        headers (list): the headers of a message from a Kafka topic
            generated by the Sources service and having event type
            "Application.unpause"
    """
    (
        account_number,
        org_id,
        application_id,
    ) = sources.extract_ids_from_kafka_message(message, headers)

    if (account_number is None and org_id is None) or application_id is None:
        logger.error(
            _(
                "Aborting unpause. Incorrect message details. "
                "account_number=%(account_number)s org_id=%(org_id)s "
                "application_id=%(application_id)s"
            ),
            {
                "account_number": account_number,
                "org_id": org_id,
                "application_id": application_id,
            },
        )
        return

    try:
        cloud_account = CloudAccount.objects.get(platform_application_id=application_id)
        with lock_task_for_user_ids([cloud_account.user.id]):
            cloud_account.platform_application_is_paused = False
            cloud_account.save()
            cloud_account.enable()
    except CloudAccount.DoesNotExist:
        logger.info(
            _(
                "CloudAccount for application ID %(application_id)s cannot unpause "
                "because it does not exist"
            ),
            {"application_id": application_id},
        )


@retriable_shared_task(
    autoretry_for=(KafkaProducerException,),
    name="api.tasks.notify_application_availability_task",
)
def notify_application_availability_task(
    account_number,
    org_id,
    application_id,
    availability_status,
    availability_status_error="",
):
    """
    Update Sources application's availability status.

    This is a task wrapper to the sources.notify_application_availability
    method which sends the availability_status Kafka message to Sources.

    Args:
        account_number (str): Account number identifier
        org_id (str): Org Id identifier
        application_id (int): Platform insights application id
        availability_status (string): Availability status to set
        availability_status_error (string): Optional status error
    """
    try:
        sources.notify_application_availability(
            account_number,
            org_id,
            application_id,
            availability_status,
            availability_status_error,
        )
    except KafkaProducerException:
        raise
