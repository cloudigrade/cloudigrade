"""Helper utility module to wrap up common AWS IAM operations."""
import boto3


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
