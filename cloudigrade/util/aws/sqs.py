"""Helper utility module to wrap up common AWS SQS operations."""
import json
import logging
import math
import uuid

import boto3
import jsonpickle
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _

from util import aws
from util.exceptions import InvalidArn

logger = logging.getLogger(__name__)

QUEUE_NAME_LENGTH_MAX = 80  # AWS SQS's maximum name length.
RETENTION_DEFAULT = 345600  # "4 days" is AWS SQS's default retention time.
RETENTION_MAXIMUM = 1209600  # "14 days" is AWS SQS's maximum retention time.
SQS_SEND_BATCH_SIZE = 10  # boto3 supports sending up to 10 items.
SQS_RECEIVE_BATCH_SIZE = 10  # boto3 supports receiving of up to 10 items.


def _get_queue(queue_url):
    """
    Get the SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.

    Returns:
        Queue: The SQS Queue boto3 resource for the given queue_url.

    """
    region = settings.SQS_DEFAULT_REGION
    queue = boto3.resource("sqs", region_name=region).Queue(queue_url)
    return queue


def receive_messages_from_queue(queue_url, max_number=10, wait_time=10):
    """
    Get message objects from SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        max_number (int): Maximum number of messages to receive.
        wait_time (int): Wait time in seconds to receive any messages.

    Returns:
        list[Message]: A list of message objects.

    """
    sqs_queue = _get_queue(queue_url)
    messages = sqs_queue.receive_messages(
        MaxNumberOfMessages=max_number, WaitTimeSeconds=wait_time,
    )

    return messages


def yield_messages_from_queue(
    queue_url, max_number=settings.AWS_SQS_MAX_YIELD_COUNT, wait_time=10
):
    """
    Yield message objects from SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        max_number (int): Maximum number of messages to receive.
        wait_time (int): Wait time in seconds to receive any messages.

    Yields:
        Message: An SQS message object.

    """
    sqs_queue = _get_queue(queue_url)
    messages_received = 0
    try:
        while messages_received < max_number:
            try:
                messages = sqs_queue.receive_messages(
                    MaxNumberOfMessages=1, WaitTimeSeconds=wait_time,
                )
                if not messages:
                    break
                for message in messages:
                    messages_received += 1
                    yield message
            except StopIteration:
                return
    except ClientError as e:
        if e.response["Error"]["Code"].endswith(".NonExistentQueue"):
            logger.warning(_("Queue does not yet exist at %s"), queue_url)
        else:
            raise


def delete_messages_from_queue(queue_url, messages):
    """
    Delete message objects from SQS queue.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        messages (list[Message]): A list of message objects to delete.

    Returns:
        dict: The response from the delete call.

    """
    if not messages:
        logger.debug(
            _(
                "%(label)s received no messages for deletion. Queue URL "
                "%(queue_url)s"
            ),
            {"label": "delete_messages_from_queue", "queue_url": queue_url},
        )
        return {}

    sqs_queue = _get_queue(queue_url)

    messages_to_delete = [
        {"Id": message.message_id, "ReceiptHandle": message._receipt_handle}
        for message in messages
    ]

    response = sqs_queue.delete_messages(Entries=messages_to_delete)

    # TODO: Deal with success/failure of message deletes
    return response


def extract_sqs_message(message, service="s3"):
    """
    Parse SQS message for service-specific content.

    Args:
        message (boto3.SQS.Message): The Message object.
        service (str): The AWS service the message refers to.

    Returns:
        list(dict): List of message records.

    """
    extracted_records = []
    message_body = json.loads(message.body)
    for record in message_body.get("Records", []):
        extracted_records.append(record[service])
    return extracted_records


def get_sqs_queue_url(queue_name):
    """
    Get the SQS queue URL for the given queue name.

    This has the side-effect on ensuring that the queue exists.

    Args:
        queue_name (str): the name of the target SQS queue

    Returns:
        str: the queue's URL.

    """
    region = settings.SQS_DEFAULT_REGION
    sqs = boto3.client("sqs", region_name=region)
    try:
        return sqs.get_queue_url(QueueName=queue_name)["QueueUrl"]
    except ClientError as e:
        if e.response["Error"]["Code"].endswith(".NonExistentQueue"):
            return create_queue(queue_name)
        raise


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
    dlq_name = "{}-dlq".format(source_queue_name[: QUEUE_NAME_LENGTH_MAX - 4])
    dlq_url = create_queue(dlq_name, with_dlq=False, retention_period=RETENTION_MAXIMUM)
    dlq_arn = sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"])[
        "Attributes"
    ]["QueueArn"]
    return dlq_arn


def add_messages_to_queue(queue_name, messages):
    """
    Send messages to an SQS queue.

    Args:
        queue_name (str): The queue to add messages to
        messages (list[dict]): A list of message dictionaries. The message
            dicts will be serialized as JSON strings.
    """
    queue_url = aws.get_sqs_queue_url(queue_name)
    sqs = boto3.client("sqs")

    wrapped_messages = [_sqs_wrap_message(message) for message in messages]
    batch_count = math.ceil(len(messages) / SQS_SEND_BATCH_SIZE)

    for batch_num in range(batch_count):
        start_pos = batch_num * SQS_SEND_BATCH_SIZE
        end_pos = start_pos + SQS_SEND_BATCH_SIZE - 1
        batch = wrapped_messages[start_pos:end_pos]
        sqs.send_message_batch(QueueUrl=queue_url, Entries=batch)


def _sqs_wrap_message(message):
    """
    Wrap the message in a dict for SQS batch sending.

    Args:
        message (object): message to encode and wrap

    Returns:
        dict: structured entry for sending to send_message_batch

    """
    return {
        "Id": str(uuid.uuid4()),
        # Yes, the outgoing message uses MessageBody, not Body.
        "MessageBody": jsonpickle.encode(message),
    }


def read_messages_from_queue(queue_name, max_count=1):
    """
    Read messages (up to max_count) from an SQS queue.

    Args:
        queue_name (str): The queue to read messages from
        max_count (int): Max number of messages to read

    Returns:
        list[object]: The de-queued messages.

    """
    queue_url = aws.get_sqs_queue_url(queue_name)
    sqs = boto3.client("sqs")
    sqs_messages = []
    max_batch_size = min(SQS_RECEIVE_BATCH_SIZE, max_count)
    for __ in range(max_count):
        # Because receive_message does *not* actually reliably return
        # MaxNumberOfMessages number of messages especially (read the docs),
        # our iteration count is actually max_count and we have some
        # conditions at the end that break us out when we reach the true end.
        new_messages = sqs.receive_message(
            QueueUrl=queue_url, MaxNumberOfMessages=max_batch_size
        ).get("Messages", [])
        if len(new_messages) == 0:
            break
        sqs_messages.extend(new_messages)
        if len(sqs_messages) >= max_count:
            break
    messages = []
    for sqs_message in sqs_messages:
        try:
            unwrapped = _sqs_unwrap_message(sqs_message)
            sqs.delete_message(
                QueueUrl=queue_url, ReceiptHandle=sqs_message["ReceiptHandle"],
            )
            messages.append(unwrapped)
        except ClientError as e:
            # I'm not sure exactly what exceptions could land here, but we
            # probably should log them, stop attempting further deletes, and
            # return what we have received (and thus deleted!) so far.
            logger.error(
                _(
                    "Unexpected error when attempting to read from %(queue)s: "
                    "%(error)s"
                ),
                {"queue": queue_url, "error": getattr(e, "response", {}).get("Error")},
            )
            logger.exception(e)
            break
    return messages


def _sqs_unwrap_message(sqs_message):
    """
    Unwrap the sqs_message to get the original message.

    Args:
        sqs_message (dict): object to unwrap and decode

    Returns:
        object: the unwrapped and decoded message object

    """
    return jsonpickle.decode(
        # Yes, the response has Body, not MessageBody.
        sqs_message["Body"]
    )
