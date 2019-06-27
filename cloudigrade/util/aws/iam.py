"""Helper utility module to wrap up common AWS IAM operations."""
import json

import boto3
from django.utils.translation import gettext as _

from util.aws.sts import (
    _get_primary_account_id,
    cloudigrade_policy,
    get_session_account_id,
)
from util.exceptions import AwsPolicyCreationException

policy_name_pattern = 'cloudigrade-policy-for-{aws_account_id}'
role_name_pattern = 'cloudigrade-role-for-{aws_account_id}'


def get_session_from_access_key(
    access_key_id, secret_access_key, region_name='us-east-1'
):
    """
    Return a new session using the customer AWS access key credentials.

    Args:
        access_key_id (str): AWS access key ID for the Session.
        secret_access_key (str): AWS secret access key for the Session.
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


def get_standard_role_name_and_arn(session):
    """
    Get cloudigrade's standard role name and ARN for customer AWS accounts.

    Returns:
        tuple(str, str) of the role name and role arn.

    """
    customer_account_id = get_session_account_id(session)
    role_name = role_name_pattern.format(
        aws_account_id=_get_primary_account_id()
    )
    arn = 'arn:aws:iam::{customer_account_id}:role/{role_name}'.format(
        customer_account_id=customer_account_id, role_name=role_name
    )
    return (role_name, arn)


def ensure_cloudigrade_policy(session):
    """
    Ensure that the AWS session's account has a cloudigrade IAM Policy.

    This has the potential side effect of creating an appropriate policy if one
    does not yet exist *or* updating the existing policy if one exists matching
    our naming conventions.

    Args:
        session (boto3.Session):

    Returns:
        tuple(str, str) of the policy name and policy arn.

    """
    policy_document = json.dumps(cloudigrade_policy)
    policy_name, policy_arn = get_standard_policy_name_and_arn(session)

    iam_client = session.client('iam')
    try:
        policy = iam_client.get_policy(PolicyArn=policy_arn)
    except iam_client.exceptions.NoSuchEntityException:
        policy = None

    if policy is None:
        policy = iam_client.create_policy(
            PolicyName=policy_name, PolicyDocument=policy_document
        )
        created_arn = policy.get('Policy', {}).get('Arn', None)
        if created_arn != policy_arn:
            raise AwsPolicyCreationException(
                _(
                    'Created policy ARN "%{created_arn}" does not match '
                    'expected policy ARN "%{policy_arn}"'
                ).format(created_arn=created_arn, policy_arn=policy_arn)
            )
        return (policy_name, policy_arn)

    policy_versions = iam_client.list_policy_versions(
        PolicyArn=policy_arn
    ).get('Versions', [])

    # Find and delete the oldest not-default version because AWS caps the
    # number of versions arbitrarily low.
    oldest_not_default_version_id = None
    for version_data in sorted(policy_versions, key=lambda v: v['CreateDate']):
        if not version_data['IsDefaultVersion']:
            oldest_not_default_version_id = version_data['VersionId']
            break
    if oldest_not_default_version_id is not None:
        iam_client.delete_policy_version(
            PolicyArn=policy_arn, VersionId=oldest_not_default_version_id
        )

    # Now we should be able to safely create a new version of the policy.
    iam_client.create_policy_version(
        PolicyArn=policy_arn, PolicyDocument=policy_document, SetAsDefault=True
    )
    return (policy_name, policy_arn)
