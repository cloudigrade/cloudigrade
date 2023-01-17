"""Helper utility module to wrap up common AWS SQS operations."""
import json
import logging

import boto3
from botocore.exceptions import ClientError
from cache_memoize import cache_memoize
from django.conf import settings
from django.utils.translation import gettext as _

from util import aws
from util.exceptions import InvalidArn

logger = logging.getLogger(__name__)

QUEUE_NAME_LENGTH_MAX = 80  # AWS SQS's maximum name length.
RETENTION_DEFAULT = 345600  # "4 days" is AWS SQS's default retention time.
RETENTION_MAXIMUM = 1209600  # "14 days" is AWS SQS's maximum retention time.


@cache_memoize(settings.CACHE_TTL_DEFAULT, cache_alias="locmem")
def get_sqs_queue_url(queue_name, region=settings.SQS_DEFAULT_REGION):
    """
    Get the SQS queue URL for the given queue name.

    This has the side-effect on ensuring that the queue exists.

    Args:
        queue_name (str): the name of the target SQS queue
        region (str): AWS region hosting the target SQS queue

    Returns:
        str: the queue's URL.

    """
    sqs = boto3.client("sqs", region_name=region)
    try:
        return sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    except ClientError as e:
        if e.response["Error"]["Code"].endswith(".NonExistentQueue"):
            return create_queue(queue_name)
        raise


def get_sqs_approximate_number_of_messages(queue_url):
    """Get approximate number of messages on SQS queue."""
    region = settings.SQS_DEFAULT_REGION
    sqs_client = boto3.client("sqs", region_name=region)

    try:
        response = sqs_client.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
        )
        return int(response["Attributes"]["ApproximateNumberOfMessages"])
    except ClientError as e:
        error_code = getattr(e, "response", {}).get("Error", {}).get("Code", None)
        if str(error_code).endswith(".NonExistentQueue"):
            logger.warning(_("Queue does not exist at %s"), queue_url)
        else:
            logger.exception(
                _(
                    "Unexpected ClientError %(code)s from "
                    "get_queue_attributes using queue url: %(queue_url)s %(e)s"
                ),
                {"queue_url": queue_url, "code": error_code, "e": e},
            )
    except Exception as e:
        logger.exception(
            _(
                "Unexpected not-ClientError exception from "
                "get_queue_attributes using queue url: %(queue_url)s %(e)s"
            ),
            {"queue_url": queue_url, "e": e},
        )
    return None


def create_queue(queue_name, with_dlq=True, retention_period=RETENTION_DEFAULT):
    """
    Create an SQS queue and return its URL.

    Args:
        queue_name (str): the name of the new queue
        with_dlq (bool): should the queue include a DLQ redrive policy
        retention_period (int): number of seconds to retain messages

    Returns:
        str: the URL for the created queue

    """
    region = settings.SQS_DEFAULT_REGION
    sqs = boto3.client("sqs", region_name=region)
    attributes = {
        "MessageRetentionPeriod": str(retention_period),  # AWS wants a str.
    }

    logger.info('Creating SQS queue "%s"', queue_name)
    queue_url = sqs.create_queue(QueueName=queue_name)["QueueUrl"]
    sqs.set_queue_attributes(QueueUrl=queue_url, Attributes=attributes)

    if with_dlq:
        ensure_queue_has_dlq(queue_name, queue_url)

    return queue_url


def set_visibility_timeout(queue_name, timeout):
    """Set the SQS queue visibility timeout."""
    region = settings.SQS_DEFAULT_REGION
    sqs_client = boto3.client("sqs", region_name=region)
    attributes = {
        "VisibilityTimeout": str(timeout),  # AWS wants a str.
    }
    queue_url = get_sqs_queue_url(queue_name)
    sqs_client.set_queue_attributes(QueueUrl=queue_url, Attributes=attributes)


def ensure_queue_has_dlq(source_queue_name, source_queue_url):
    """
    Ensure that the given SQS queue is configured with a DLQ redrive policy.

    Args:
        source_queue_name (str): the queue name that should have a DLQ
        source_queue_URL (str): the queue URL that should have a DLQ
    """
    region = settings.SQS_DEFAULT_REGION
    sqs = boto3.client("sqs", region_name=region)
    redrive_policy = (
        sqs.get_queue_attributes(
            QueueUrl=source_queue_url, AttributeNames=["RedrivePolicy"]
        )
        .get("Attributes", {})
        .get("RedrivePolicy", "{}")
    )
    redrive_policy = json.loads(redrive_policy)

    if validate_redrive_policy(source_queue_name, redrive_policy):
        return

    logger.info('SQS queue "%s" needs an updated redrive policy', source_queue_name)
    dlq_arn = create_dlq(source_queue_name)

    redrive_policy = {
        "deadLetterTargetArn": dlq_arn,
        "maxReceiveCount": settings.AWS_SQS_MAX_RECEIVE_COUNT,
    }
    attributes = {
        "RedrivePolicy": json.dumps(redrive_policy),
    }
    logger.info(
        'Assigning SQS queue "%(queue)s" redrive policy: %(policy)s',
        {"queue": source_queue_name, "policy": redrive_policy},
    )
    sqs.set_queue_attributes(QueueUrl=source_queue_url, Attributes=attributes)


def validate_redrive_policy(source_queue_name, redrive_policy):
    """
    Validate the queue redrive policy has an accessible DLQ.

    Args:
        source_queue_name (str): the queue name that should have a DLQ
        redrive_policy (dict): the redrive policy

    Returns:
        bool: True if policy appears to be valid, else False.

    """
    logger.info(
        'SQS queue "%(queue)s" already has a redrive policy: ' "%(policy)s",
        {"queue": source_queue_name, "policy": redrive_policy},
    )

    dlq_queue_arn = redrive_policy.get("deadLetterTargetArn")

    if not dlq_queue_arn:
        return False

    try:
        dlq_queue_name = aws.AwsArn(dlq_queue_arn).resource
    except InvalidArn:
        return False

    try:
        region = settings.SQS_DEFAULT_REGION
        sqs = boto3.client("sqs", region_name=region)
        sqs.get_queue_url(QueueName=dlq_queue_name)["QueueUrl"]
        queue_exists = True
    except ClientError as e:
        if e.response["Error"]["Code"].endswith(".NonExistentQueue"):
            queue_exists = False
        else:
            raise

    return queue_exists


def get_sqs_queue_dlq_name(source_queue_name):
    """Get the standard DLQ queue name for the given queue name."""
    return "{}-dlq".format(source_queue_name[: QUEUE_NAME_LENGTH_MAX - 4])


def create_dlq(source_queue_name):
    """
    Create a DLQ and return its created ARN.

    Args:
        source_queue_name (str): the name of the source queue

    Returns:
        str: the ARN for the create DLQ.

    """
    region = settings.SQS_DEFAULT_REGION
    sqs = boto3.client("sqs", region_name=region)
    dlq_name = get_sqs_queue_dlq_name(source_queue_name)
    dlq_url = create_queue(dlq_name, with_dlq=False, retention_period=RETENTION_MAXIMUM)
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    return dlq_arn
