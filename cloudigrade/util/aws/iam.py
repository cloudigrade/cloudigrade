"""Helper utility module to wrap up common AWS IAM operations."""
import json
import logging

import boto3
from django.utils.translation import gettext as _

from util.aws.sts import (
    _get_primary_account_id,
    cloudigrade_policy,
    get_session_account_id,
)
from util.exceptions import (
    AwsPolicyCreationException,
    AwsRoleCreationException,
)

logger = logging.getLogger(__name__)
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
        session (boto3.Session): temporary session tied to a customer account

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


def get_standard_assume_role_policy_document():
    """
    Get cloudigrade's standard AssumeRolePolicyDocument for customer IAM Roles.

    Returns:
        str: the Policy document

    """
    aws_account_id = _get_primary_account_id()
    cloudigrade_account_root_arn = f'arn:aws:iam::{aws_account_id}:root'
    document_dict = {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Principal': {'AWS': cloudigrade_account_root_arn},
                'Action': 'sts:AssumeRole',
                'Condition': {},
            }
        ],
    }
    document_str = json.dumps(document_dict)
    return document_str


def ensure_cloudigrade_role(session, policy_arn):
    """
    Ensure that the AWS session's account has a cloudigrade IAM Role.

    This has the potential side effect of creating an appropriate Role if one
    does not yet exist *or* updating the existing Role if one exists matching
    our naming conventions.

    This function requires that the cloudigrade IAM Policy has already been
    created in the customer's account and is valid. The new Role created here
    will be associated with that Policy.

    Args:
        session (boto3.Session): temporary session tied to a customer account
        policy_arn (str): the cloudigrade Policy's ARN in the customer account

    Returns:
        tuple(str, str) of the Role name and Policy ARN.

    """
    role_name, role_arn = get_standard_role_name_and_arn(session)
    assume_role_policy_document = get_standard_assume_role_policy_document()

    iam_client = session.client('iam')

    # Step 1: Ensure the Role exists.
    try:
        role = iam_client.get_role(RoleName=role_name)
    except iam_client.exceptions.NoSuchEntityException:
        role = None
    if role is None:
        role = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=assume_role_policy_document,
        )
        created_arn = role.get('Role', {}).get('Arn')
        if created_arn != role_arn:
            raise AwsRoleCreationException(
                _(
                    'Created role ARN "{created_arn}" does not match '
                    'expected role ARN "{role_arn}"'
                ).format(created_arn=created_arn, role_arn=role_arn)
            )
        created_name = role.get('Role', {}).get('RoleName')
        if created_name != role_name:
            raise AwsRoleCreationException(
                _(
                    'Created role name "{created_name}" does not match '
                    'expected role name "{role_name}"'
                ).format(created_name=created_name, role_name=role_name)
            )

    # Step 2: Ensure the Role has our assume role policy document.
    existing_assume_role_policy_document = json.dumps(
        role.get('Role', {}).get('AssumeRolePolicyDocument')
    )
    if existing_assume_role_policy_document != assume_role_policy_document:
        logger.warning(
            _(
                'Existing AssumeRolePolicyDocument for Role %(role_arn)s does'
                'not match expected value (old: %(document)s)'
            ),
            {
                'role_arn': role_arn,
                'document': existing_assume_role_policy_document,
            },
        )
        iam_client.update_assume_role_policy(
            RoleName=role_name, PolicyDocument=assume_role_policy_document
        )

    # Step 3: Ensure the Role has the customer's cloudigrade Policy attached.
    attached_policies = iam_client.list_attached_role_policies(
        RoleName=role_name
    ).get('AttachedPolicies', [])
    attached_policy_found = False
    for attached_policy in attached_policies:
        if attached_policy.get('PolicyArn') == policy_arn:
            attached_policy_found = True
            break
    if not attached_policy_found:
        logger.info(
            _('Attaching policy ARN %(policy_arn)s to role ARN %(role_arn)s'),
            {'policy_arn': policy_arn, 'role_arn': role_arn},
        )
        iam_client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)

    return (role_name, role_arn)
