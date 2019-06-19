"""Helper utility module to wrap up common AWS IAM operations."""
import boto3

from util.aws.sts import _get_primary_account_id, get_session_account_id

policy_name_pattern = 'cloudigrade-policy-for-{aws_account_id}'


def get_session_from_access_key(
    access_key_id, secret_access_key, region_name='us-east-1'
):
    """
    Return a new session using the customer AWS access key credentials.

    Args:
        access_key_id (str): AWS access key ID for ths Session.
        secret_access_key (str): AWS secret access key for ths Session.
        region_name (str): Default AWS Region for the Session.

    Returns:
        boto3.Session: A temporary session tied to a customer account

    """
    session = boto3.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=region_name,
    )
    return session


def get_standard_policy_name_and_arn(session):
    """
    Get cloudigrade's standard policy name and ARN for customer AWS accounts.

    Returns:
        tuple(str, str) of the policy name and policy arn.

    """
    customer_account_id = get_session_account_id(session)
    policy_name = policy_name_pattern.format(
        aws_account_id=_get_primary_account_id()
    )
    arn = 'arn:aws:iam::{customer_account_id}:policy/{policy_name}'.format(
        customer_account_id=customer_account_id, policy_name=policy_name
    )
    return (policy_name, arn)
