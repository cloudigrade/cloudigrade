"""Helper utility module to wrap up common AWS operations."""
import boto3


def get_regions(service_name='ec2'):
    """
    Get the full list of available AWS regions for the given service.

    Args:
        service_name (str): Name of AWS service. Default is 'ec2'.

    Returns:
        list: The available AWS region names.

    """
    return boto3.Session().get_available_regions(service_name)


def get_credentials_for_arn(arn, session_name='temp-session'):
    """
    Get the credentials for a given ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.
        session_name (str): Optional custom name for the session.

    Returns:
        dict: The credentials we can use to establish a session.

    """
    sts = boto3.client('sts')
    assume_role_object = sts.assume_role(
        RoleArn=arn,
        RoleSessionName=session_name,
    )
    return assume_role_object['Credentials']
