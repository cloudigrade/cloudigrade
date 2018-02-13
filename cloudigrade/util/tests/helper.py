"""Helper functions for generating test data."""
import random

import faker

MAX_AWS_ACCOUNT_ID = 999999999999


def generate_dummy_aws_account_id():
    """Generate a dummy AWS Account ID for testing purposes."""
    return str(random.randrange(MAX_AWS_ACCOUNT_ID))


def generate_dummy_arn(account_id=None):
    """Generate a dummy AWS ARN for testing purposes."""
    if account_id is None:
        account_id = generate_dummy_aws_account_id()
    words = faker.Faker().name().replace(' ', '_')
    arn = f'arn:aws:iam::{account_id}:role/{words}'
    return arn
