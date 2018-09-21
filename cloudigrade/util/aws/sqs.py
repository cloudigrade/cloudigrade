"""Helper utility module to wrap up common AWS SQS operations."""
import json
import logging

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

QUEUE_NAME_LENGTH_MAX = 80  # AWS SQS's maximum name length.
RETENTION_DEFAULT = 345600  # "4 days" is AWS SQS's default retention time.
RETENTION_MAXIMUM = 1209600  # "14 days" is AWS SQS's maximum retention time.


def _get_queue(queue_url):
    """
    Get the SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.

    Returns:
        Queue: The SQS Queue boto3 resource for the given queue_url.

    """
    region = settings.SQS_DEFAULT_REGION
    queue = boto3.resource('sqs', region_name=region).Queue(queue_url)
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
        MaxNumberOfMessages=max_number,
        WaitTimeSeconds=wait_time,
    )

    return messages


def yield_messages_from_queue(queue_url, max_number=10, wait_time=10):
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
    while messages_received < max_number:
        messages = sqs_queue.receive_messages(
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_time,
        )
        if not messages:
            break
        for message in messages:
            messages_received += 1
            yield message


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
            _('{0} received no messages for deletion.   Queue URL {1}').format(
                'delete_messages_from_queue', queue_url))
        return {}

    sqs_queue = _get_queue(queue_url)

    messages_to_delete = [
        {
            'Id': message.message_id,
            'ReceiptHandle': message._receipt_handle
        }
        for message in messages
    ]

    response = sqs_queue.delete_messages(
        Entries=messages_to_delete
    )

    # TODO: Deal with success/failure of message deletes
    return response


def extract_sqs_message(message, service='s3'):
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
    for record in message_body.get('Records', []):
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
    sqs = boto3.client('sqs', region_name=region)
    try:
        return sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
    except ClientError as e:
        if e.response['Error']['Code'].endswith('.NonExistentQueue'):
            return create_queue(queue_name)
        raise


def create_queue(queue_name, with_dlq=True,
                 retention_period=RETENTION_DEFAULT):
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
    sqs = boto3.client('sqs', region_name=region)
    attributes = {
        'MessageRetentionPeriod': str(retention_period),  # AWS wants a str.
    }

    logger.info('Creating SQS queue "{}"'.format(queue_name))
    queue_url = sqs.create_queue(QueueName=queue_name)['QueueUrl']
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
    sqs = boto3.client('sqs', region_name=region)
    redrive_policy = sqs.get_queue_attributes(
        QueueUrl=source_queue_url, AttributeNames=['RedrivePolicy']
    ).get('Attributes', {}).get('RedrivePolicy', '{}')
    redrive_policy = json.loads(redrive_policy)

    if redrive_policy:
        logger.info('SQS queue "{}" already has a redrive policy: {}'.format(
            source_queue_name, redrive_policy))
        return

    dlq_arn = create_dlq(source_queue_name)

    redrive_policy = {
        'deadLetterTargetArn': dlq_arn,
        'maxReceiveCount': settings.AWS_SQS_MAX_RECEIVE_COUNT,
    }
    attributes = {
        'RedrivePolicy': json.dumps(redrive_policy),
    }
    logger.info('Assigning SQS queue "{}" redrive policy: {}'.format(
        source_queue_name, redrive_policy))
    sqs.set_queue_attributes(QueueUrl=source_queue_url, Attributes=attributes)


def create_dlq(source_queue_name):
    """
    Create a DLQ and return its created ARN.

    Args:
        source_queue_name (str): the name of the source queue

    Returns:
        str: the ARN for the create DLQ.

    """
    region = settings.SQS_DEFAULT_REGION
    sqs = boto3.client('sqs', region_name=region)
    dlq_name = '{}-dlq'.format(source_queue_name[:QUEUE_NAME_LENGTH_MAX - 4])
    dlq_url = create_queue(
        dlq_name, with_dlq=False, retention_period=RETENTION_MAXIMUM
    )
    dlq_arn = sqs.get_queue_attributes(
        QueueUrl=dlq_url, AttributeNames=['QueueArn']
    )['Attributes']['QueueArn']
    return dlq_arn
