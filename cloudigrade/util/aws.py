"""Helper utility module to wrap up common AWS operations."""
import decimal
import enum
import gzip
import json
import logging

import boto3
from botocore.exceptions import ClientError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

cloudigrade_policy = {
    'Version': '2012-10-17',
    'Statement': [
        {
            'Sid': 'CloudigradePolicy',
            'Effect': 'Allow',
            'Action': [
                'ec2:DescribeImages',
                'ec2:DescribeInstances',
                'ec2:ModifySnapshotAttribute',
                'ec2:DescribeSnapshotAttribute',
                'ec2:ModifyImageAttribute',
                'ec2:DescribeSnapshots'
            ],
            'Resource': '*'
        }
    ]
}


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


def get_session(arn, region_name='us-east-1'):
    """
    Return a session using the customer AWS account role ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.
        region_name (str): Default AWS Region to associate newly
        created clients with.

    Returns:
        boto3.Session: A temporary session tied to a customer account

    """
    sts = boto3.client('sts')
    response = sts.assume_role(
        Policy=json.dumps(cloudigrade_policy),
        RoleArn=arn,
        RoleSessionName=f'cloudigrade-{extract_account_id_from_arn(arn)}'
    )
    response = response['Credentials']
    return boto3.Session(
        aws_access_key_id=response['AccessKeyId'],
        aws_secret_access_key=response['SecretAccessKey'],
        aws_session_token=response['SessionToken'],
        region_name=region_name
    )


def get_regions(session, service_name='ec2'):
    """
    Get the full list of available AWS regions for the given service.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        service_name (str): Name of AWS service. Default is 'ec2'.

    Returns:
        list: The available AWS region names.

    """
    return session.get_available_regions(service_name)


def get_running_instances(session):
    """
    Find all running EC2 instances visible to the given ARN.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.

    """
    running_instances = {}

    for region_name in get_regions(session):

        ec2 = session.client('ec2', region_name=region_name)
        logger.debug(_(f'Describing instances in {region_name}'))
        instances = ec2.describe_instances()
        for reservation in instances.get('Reservations', []):
            running_instances[region_name] = [
                instance for instance in reservation.get('Instances', [])
                if InstanceState.is_running(instance['State']['Code'])
            ]

    return running_instances


def verify_account_access(session):
    """
    Check role for proper access to AWS APIs.

    Args:
        session (boto3.Session): A temporary session tied to a customer account

    Returns:
        bool: Whether role is verified.

    """
    success = True
    for action in cloudigrade_policy['Statement'][0]['Action']:
        if not _verify_policy_action(session, action):
            # Mark as failure, but keep looping so we can see each specific
            # failure in logs
            success = False
    return success


def _verify_policy_action(session, action):
    """
    Check to see if we have access to a specific action.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        action (str): The policy action to check

    Returns:
        bool: Whether the action is allowed, or not.

    """
    dry_run_operation = 'DryRunOperation'
    unauthorized_operation = 'UnauthorizedOperation'

    ec2 = session.client('ec2')

    try:
        if action == 'ec2:DescribeImages':
            ec2.describe_images(DryRun=True)
        elif action == 'ec2:DescribeInstances':
            ec2.describe_instances(DryRun=True)
        elif action == 'ec2:DescribeSnapshotAttribute':
            ec2.describe_snapshot_attribute(
                DryRun=True,
                SnapshotId='string',
                Attribute='productCodes'
            )
        elif action == 'ec2:DescribeSnapshots':
            ec2.describe_snapshots(DryRun=True)
        elif action == 'ec2:ModifySnapshotAttribute':
            ec2.modify_snapshot_attribute(
                SnapshotId='string',
                DryRun=True,
                Attribute='productCodes',
                GroupNames=['string', ]
            )
        elif action == 'ec2:ModifyImageAttribute':
            ec2.modify_image_attribute(
                Attribute='description',
                ImageId='string',
                DryRun=True
            )
        else:
            logger.warning(_(f'No test case exists for action "{action}"'))
            return False
    except ClientError as e:
        if e.response['Error']['Code'] == dry_run_operation:
            logger.debug(_(f'Verified access to "{action}"'))
            return True
        elif e.response['Error']['Code'] == unauthorized_operation:
            logger.warning(_(f'No access to "{action}"'))
            return False
        else:
            raise e


def receive_message_from_queue(queue_url):
    """
    Get message objects from SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.

    Returns:
        list[Message]: A list of message objects.

    """
    sqs_queue = boto3.resource('sqs').Queue(queue_url)

    messages = sqs_queue.receive_messages(
        MaxNumberOfMessages=10,
        WaitTimeSeconds=10
    )

    return messages


def delete_message_from_queue(queue_url, messages):
    """
    Delete message objects from SQS queue.

    Args:
        queue_url (str): The AWS assigned URL for the queue.
        messages (list[Message]): A list of message objects to delete.

    Returns:
        dict: The response from the delete call.

    """
    sqs_queue = boto3.resource('sqs').Queue(queue_url)

    messages_to_delete = [
        {
            'Id': message.message_id,
            'ReceiptHandle': message._receipt_handle
        }
        for message in messages
    ]

    response = sqs_queue.delete_messages(
        Entries=messages_to_delete
    )

    # TODO: Deal with success/failure of message deletes
    return response


def get_object_content_from_s3(bucket, key, compression='gzip'):
    """
    Get the file contents from an S3 object.

    Args:
        bucket (str): The S3 bucket the object is stored in.
        key (str): The S3 object key identified.
        compression (str): The compression format for the stored file object.

    Returns:
        str: The string contents of the file object.

    """
    content = None
    s3_object = boto3.resource('s3').Object(bucket, key)

    object_bytes = s3_object.get()['Body'].read()

    if compression == 'gzip':
        content = gzip.decompress(object_bytes).decode('utf-8')
    elif compression is None:
        try:
            content = object_bytes.decode('utf-8')
        except UnicodeDecodeError as e:
            logger.error(_(e))
    else:
        logger.error(_('Unsupported compression format'))

    return content
