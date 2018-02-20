"""Helper utility module to wrap up common AWS operations."""
import decimal
import enum
import logging

import boto3
from botocore.exceptions import ClientError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class InstanceState(enum.Enum):
    """
    Enumeration of EC2 Instance state codes.

    See also:
        https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_InstanceState.html

    """

    pending = 0
    running = 16
    shutting_down = 32
    terminated = 48
    stopping = 64
    stopped = 80

    @classmethod
    def is_running(cls, code):
        """
        Check if the given code is effectively a running state.

        Args:
            code (int): The code from an EC2 Instance state.

        Returns:
            bool: True if we consider the instance to be running else False.

        """
        return code == cls.running.value


def extract_account_id_from_arn(arn):
    """
    Extract the AWS Account ID from the given ARN.

    Args:
        arn (str): A well-formed Amazon Resource Name.

    Returns:
        Decimal: The Account ID found in the ARN.

    """
    return decimal.Decimal(arn.split(':')[4])


def get_regions(service_name='ec2'):
    """
    Get the full list of available AWS regions for the given service.

    Args:
        service_name (str): Name of AWS service. Default is 'ec2'.

    Returns:
        list: The available AWS region names.

    """
    return boto3.Session().get_available_regions(service_name)


def get_credentials_for_arn(arn):
    """
    Get the credentials for a given ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.

    Returns:
        dict: The credentials we can use to establish a session.

    """
    sts = boto3.client('sts')
    session_name = 'temp-session'

    # TODO: Decide if we want to limit the session length beyond
    # the default 60 minutes
    # TODO: Decide if we want to handle MFA
    assume_role_object = sts.assume_role(
        RoleArn=arn,
        RoleSessionName=session_name,
    )
    return assume_role_object['Credentials']


def get_running_instances(arn):  # TODO filter
    """
    Find all running EC2 instances visible to the given ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.

    """
    credentials = get_credentials_for_arn(arn)
    running_instances = {}

    for region_name in get_regions():
        role_session = get_assumed_session(arn, region_name, credentials)

        ec2 = role_session.client('ec2')
        logger.debug(_(f'Describing instances in {region_name} for {arn}'))
        instances = ec2.describe_instances()
        for reservation in instances.get('Reservations', []):
            running_instances[region_name] = [
                instance for instance in reservation.get('Instances', [])
                if InstanceState.is_running(instance['State']['Code'])
            ]

    return running_instances


def get_assumed_session(arn, region_name='us-east-1', credentials=None):
    """
    Return a session using the customer AWS account role.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.
        region_name (str): AWS Region to associate the session with.
        credentials (dict): Credentials returned by STS assume_role call.

    Returns:
        boto3.Session: A temporary session tied to a customer account

    """
    if credentials is None:
        credentials = get_credentials_for_arn(arn)

    return boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
        region_name=region_name)


def verify_account_access(arn):
    """
    Check role for proper access to AWS APIs.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.

    Returns:
        bool: Whether role is verifed.

    """
    role_session = get_assumed_session(arn)
    # TODO Check against IAM role JSON instead of making API calls
    try:
        ec2 = role_session.client('ec2')
        ec2.describe_instances()
    except ClientError as e:
        errmsg = _('Role session does not have required access. ' +
                   f'Call failed with error "{e}"')
        logger.error(errmsg)
        return False

    return True
