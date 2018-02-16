"""Helper functions for generating test data."""
import decimal
import random
import uuid

import faker

from util import aws

MAX_AWS_ACCOUNT_ID = 999999999999


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
                                     subnet_id=None, state=None):
    """
    Generate dummy instance to imitate 'describe instances' API response.

    All arguments are optional, and any not given will be randomly generated.

    Args:
        instance_id (str): Optional EC2 Instance ID.
        image_id (str): Optional AMI ID.
        subnet_id (str): Optional Subnet ID.
        state (aws.InstanceState): Optional known state of the Instance.

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

    mock_instance = {
        'ImageId': image_id,
        'InstanceId': instance_id,
        'State': {
            'Code': state.value,
            'Name': state.name,
        },
        'SubnetId': subnet_id,
    }
    return mock_instance
