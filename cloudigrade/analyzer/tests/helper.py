"""Helper functions for generating test data for the log analyzer."""
import json
import random
import uuid

from util.tests import helper as util_helper


def generate_mock_cloudtrail_sqs_message(bucket_name='analyzer-test-bucket',
                                         object_key='path/to/file.json.gz',
                                         receipt_handle=None,
                                         message_id=None):
    """
    Generate a Mock object that behaves like a CloudTrail SQS message.

    Args:
        bucket_name (str): optional name of the S3 bucket
        object_key (str): optional path to the S3 object
        receipt_handle (str): optional SQS message receipt handle
        queue_url (str): optional SQS queue URL

    Returns:
        Mock: populated to look and behave like a CloudTrail SQS message

    """
    if not receipt_handle:
        receipt_handle = str(uuid.uuid4())

    if not message_id:
        message_id = str(uuid.uuid4())

    mock_sqs_message_body = {
        'Records': [
            {
                's3': {
                    'bucket': {
                        'name': bucket_name,
                    },
                    'object': {
                        'key': object_key,
                    },
                },
            }
        ]
    }
    mock_message = util_helper.generate_mock_sqs_message(
        message_id,
        json.dumps(mock_sqs_message_body),
        receipt_handle
    )
    return mock_message


def generate_cloudtrail_log_record(aws_account_id, instance_ids, region=None,
                                   event_name='RunInstances', event_time=None):
    """
    Generate an example CloudTrail S3 log file's "Record" dict of an API event.

    Args:
        aws_account_id (int): The AWS account ID.
        instance_ids (list[str]): The EC2 instance IDs relevant to the event.
        region (str): optional AWS region in which the event occurred.
        event_name (str): optional AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.

    Returns:
        dict: Data that looks like a CloudTrail log Record for some API event.

    """
    if not region:
        region = random.choice(util_helper.SOME_AWS_REGIONS)
    if not event_time:
        event_time = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)

    record = {
        'awsRegion': region,
        'eventName': event_name,
        'eventSource': 'ec2.amazonaws.com',
        'eventTime': event_time.strftime(
            '%Y-%m-%dT%H:%M:%SZ'
        ),
        'eventType': 'AwsApiCall',
        'responseElements': {
            'instancesSet': {
                'items': [
                    {'instanceId': instance_id}
                    for instance_id in instance_ids
                ]
            },
        },
        'userIdentity': {
            'accountId': int(aws_account_id)
        }
    }
    return record
