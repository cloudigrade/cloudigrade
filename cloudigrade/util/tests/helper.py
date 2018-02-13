"""Helper functions for generating test data."""
import decimal
import random

import faker

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
