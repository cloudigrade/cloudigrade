"""Helper utility module to wrap up common AWS STS operations."""

import json
import logging

import boto3
from botocore.exceptions import ClientError
from django.utils.translation import gettext as _

from util.aws.arn import AwsArn

logger = logging.getLogger(__name__)

cloudigrade_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "CloudigradePolicy",
            "Effect": "Allow",
            "Action": ["sts:GetCallerIdentity"],
            "Resource": "*",
        }
    ],
}


def get_session(arn, external_id, region_name="us-east-1"):
    """
    Return a session using the customer AWS account role ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.
        external_id (str): External Id unique to the customer provided by Red Hat.
        region_name (str): Default AWS Region to associate newly
        created clients with.

    Returns:
        boto3.Session: A temporary session tied to a customer account

    """
    sts = boto3.client("sts")
    awsarn = AwsArn(arn)

    assume_role_params = {
        "Policy": json.dumps(cloudigrade_policy),
        "RoleArn": "{0}".format(awsarn),
        "RoleSessionName": "cloudigrade-{0}".format(awsarn.account_id),
    }

    # we add external id only if it is not None or not empty
    if external_id and external_id.strip():
        assume_role_params["ExternalId"] = external_id

    response = sts.assume_role(**assume_role_params)
    response = response["Credentials"]

    return boto3.Session(
        aws_access_key_id=response["AccessKeyId"],
        aws_secret_access_key=response["SecretAccessKey"],
        aws_session_token=response["SessionToken"],
        region_name=region_name,
    )


def get_session_account_id(session):
    """
    Return the account ID for the given AWS session.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        str the sessions's account ID or None if session is invalid.

    """
    try:
        sts_client = session.client("sts")
        return sts_client.get_caller_identity().get("Account")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "InvalidClientTokenId":
            logger.info(_("Invalid client token id. Cannot get session account ID."))
            return None
        raise e


def _get_primary_account_id():
    """Return the account ID for the primary AWS account."""
    return boto3.client("sts").get_caller_identity().get("Account")
