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


def generate_cloudtrail_record(aws_account_id, event_name, event_time=None,
                               region=None, request_parameters=None,
                               response_elements=None):
    """
    Generate an example CloudTrail log's "Record" dict.

    This function needs something in request_parameters or response_elements to
    produce actually meaningful output, but this is not strictly required.

    Args:
        aws_account_id (int): The AWS account ID.
        event_name (str): optional AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.
        request_parameters (dict): optional data for 'requestParameters' key.
        response_elements (dict): optional data for 'responseElements' key.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    if not region:
        region = random.choice(util_helper.SOME_AWS_REGIONS)
    if not event_time:
        event_time = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
    if not request_parameters:
        request_parameters = {}
    if not response_elements:
        response_elements = {}

    record = {
        'awsRegion': region,
        'eventName': event_name,
        'eventSource': 'ec2.amazonaws.com',
        'eventTime': event_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'requestParameters': request_parameters,
        'responseElements': response_elements,
        'userIdentity': {
            'accountId': int(aws_account_id)
        }
    }
    return record


def generate_cloudtrail_tag_set_record(aws_account_id, image_ids, tag_names,
                                       event_name='CreateTags',
                                       event_time=None, region=None):
    """
    Generate an example CloudTrail log's "Record" dict for tag setting events.

    Args:
        aws_account_id (int): The AWS account ID.
        image_ids (list[str]): The EC2 AMI IDs whose tags are changing.
        event_name (str): AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    request_parameters = {
        'resourcesSet': {
            'items': [
                {'resourceId': image_id}
                for image_id in image_ids
            ]
        },
        'tagSet': {
            'items': [
                {'key': tag_name, 'value': tag_name}
                for tag_name in tag_names
            ]
        },
    }
    record = generate_cloudtrail_record(
        aws_account_id, event_name, event_time, region,
        request_parameters=request_parameters)
    return record


def generate_cloudtrail_instances_record(aws_account_id, instance_ids,
                                         event_name='RunInstances',
                                         event_time=None, region=None):
    """
    Generate an example CloudTrail log's "Record" dict for instances event.

    Args:
        aws_account_id (int): The AWS account ID.
        instance_ids (list[str]): The EC2 instance IDs relevant to the event.
        event_name (str): optional AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    response_elements = {
        'instancesSet': {
            'items': [
                {'instanceId': instance_id}
                for instance_id in instance_ids
            ]
        },
    }
    record = generate_cloudtrail_record(
        aws_account_id, event_name, event_time, region,
        response_elements=response_elements)
    return record


def generate_cloudtrail_modify_instances_record(aws_account_id, instance_id,
                                                instance_type='t2.micro',
                                                event_time=None, region=None):
    """
    Generate an ex. CloudTrail log's "Record" dict for modify instances event.

    Args:
        aws_account_id (int): The AWS account ID.
        instance_id (str): The EC2 instance ID relevant to the event.
        instance_type (str): New instance type.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    event_name = 'ModifyInstanceAttribute'
    request_parameters = {
        'instanceId': instance_id,
        'instanceType': {
            'value': instance_type
        }
    }
    record = generate_cloudtrail_record(
        aws_account_id, event_name, event_time, region,
        request_parameters=request_parameters)
    return record
