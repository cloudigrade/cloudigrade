"""Helper utility module to wrap up common AWS operations."""
import collections
import decimal
import logging

import boto3
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


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
    session_name = 'temp-session'  # TODO Does this need to be a funciton arg?
    assume_role_object = sts.assume_role(
        RoleArn=arn,
        RoleSessionName=session_name,
    )
    return assume_role_object['Credentials']


def get_running_instances(arn):
    """
    Find all running EC2 instances visible to the given ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.

    """
    credentials = get_credentials_for_arn(arn)
    found_instances = collections.defaultdict(list)

    for region_name in get_regions():
        role_session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region_name,
        )

        ec2 = role_session.client('ec2')
        logger.debug(_(f'Describing instances in {region_name} for {arn}'))
        instances = ec2.describe_instances()
        for reservation in instances.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                found_instances[region_name].append(instance['InstanceId'])

    return dict(found_instances)
