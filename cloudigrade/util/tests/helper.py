"""Helper functions for generating test data."""
import datetime
import decimal
import random
import uuid
from unittest.mock import Mock

import faker
from dateutil import tz

from util import aws

MAX_AWS_ACCOUNT_ID = 999999999999


SOME_AWS_REGIONS = (
    'ap-northeast-1',
    'ca-central-1',
    'eu-west-1',
    'us-east-1',
    'us-east-2',
)


SOME_EC2_INSTANCE_TYPES = (
    'c5.xlarge',
    'm5.24xlarge',
    'r4.large',
    't2.large',
    't2.medium',
    't2.micro',
    't2.nano',
    't2.small',
    't2.xlarge',
    'x1e.32xlarge',
)


def generate_dummy_aws_account_id():
    """Generate a dummy AWS Account ID for testing purposes."""
    return decimal.Decimal(random.randrange(MAX_AWS_ACCOUNT_ID))


def generate_dummy_arn(account_id=None):
    """
    Generate a dummy AWS ARN for testing purposes.

    Args:
        account_id (int): Optional Account ID. Default is randomly generated.

    Returns:
        str: A well-formed, randomized ARN.

    """
    if account_id is None:
        account_id = generate_dummy_aws_account_id()
    words = faker.Faker().name().replace(' ', '_')
    arn = f'arn:aws:iam::{account_id}:role/{words}'
    return arn


def generate_dummy_describe_instance(instance_id=None, image_id=None,
                                     subnet_id=None, state=None,
                                     instance_type=None):
    """
    Generate dummy instance to imitate 'describe instances' API response.

    All arguments are optional, and any not given will be randomly generated.

    Args:
        instance_id (str): Optional EC2 Instance ID.
        image_id (str): Optional AMI ID.
        subnet_id (str): Optional Subnet ID.
        state (aws.InstanceState): Optional known state of the Instance.
        instance_type (str): Optional known EC2 type of Instance.

    Returns:
        dict: Well-formed instance data structure.

    """
    if state is None:
        state = random.choice(list(aws.InstanceState))

    if image_id is None:
        image_id = str(uuid.uuid4())

    if instance_id is None:
        instance_id = str(uuid.uuid4())

    if subnet_id is None:
        subnet_id = str(uuid.uuid4())

    if instance_type is None:
        instance_type = random.choice(SOME_EC2_INSTANCE_TYPES)

    mock_instance = {
        'ImageId': image_id,
        'InstanceId': instance_id,
        'InstanceType': instance_type,
        'State': {
            'Code': state.value,
            'Name': state.name,
        },
        'SubnetId': subnet_id,
    }
    return mock_instance


def generate_mock_ec2_instance(instance_id=None, image_id=None, subnet_id=None,
                               state=None, instance_type=None):
    """
    Generate a mocked EC2 Instance object.

    Args:
        instance_id (string): The EC2 instance id.
        instance_type (string): The EC2 instance type.
        image_id (string): The EC2 AMI image id.
        subnet (string): The EC2 subnet.

    Returns:
        Mock: A mock object with Instance-like attributes.

    """
    described_instance = generate_dummy_describe_instance(
        instance_id, image_id, subnet_id, state, instance_type
    )
    mock_instance = Mock()
    mock_instance.instance_id = described_instance['InstanceId']
    mock_instance.instance_type = described_instance['InstanceType']
    mock_instance.image_id = described_instance['ImageId']
    mock_instance.state = described_instance['State']
    mock_instance.subnet_id = described_instance['SubnetId']
    return mock_instance


def generate_mock_sqs_message(message_id, body, receipt_handle):
    """
    Generate a mocked SQS Message object.

    Args:
        message_id (string): The SQS message id.
        body (string): The message contents.
        receipt_handle (string): The SQS receipt handle.

    Returns:
        Mock: A mock object with Message-like attributes.

    """
    mock_message = Mock()
    mock_message.Id = message_id
    mock_message.ReceiptHandle = receipt_handle
    mock_message.body = body
    return mock_message


def utc_dt(*args, **kwargs):
    """Wrap datetime construction to force result to UTC.

    Returns:
        datetime.datetime

    """
    return datetime.datetime(*args, **kwargs).replace(
        tzinfo=tz.tzutc()
    )
