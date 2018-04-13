"""Helper utility module to wrap up common AWS operations."""
import enum
import gzip
import json
import logging
import re
from functools import wraps

import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from django.utils.translation import gettext as _

from util.exceptions import (AwsSnapshotCopyLimitError,
                             AwsSnapshotNotOwnedError)
from util.exceptions import InvalidArn, SnapshotNotReadyException

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

# AWS has undocumented validation on the SnapshotId field in
# snapshot related EC2 API calls.
# We are uncertain what the pattern is. Manual testing revealed
# that some codes pass and some fail, so for the time being
# the value is hard-coded.
SNAPSHOT_ID = 'snap-0f423c31dd96866b2'


class InstanceState(enum.Enum):
    """
    Enumeration of EC2 instance state codes.

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
            code (int): The code from an EC2 AwsInstance state.

        Returns:
            bool: True if we consider the instance to be running else False.

        """
        return code == cls.running.value


class AwsArn(object):
    """
    Object representing an AWS ARN.

    See also:
        https://docs.aws.amazon.com/general/latest/gr/aws-arns-and-namespaces.html

    General ARN formats:
        arn:partition:service:region:account-id:resource
        arn:partition:service:region:account-id:resourcetype/resource
        arn:partition:service:region:account-id:resourcetype:resource

    Example ARNs:
        <!-- Elastic Beanstalk application version -->
        arn:aws:elasticbeanstalk:us-east-1:123456789012:environment/My App/foo

        <!-- IAM user name -->
        arn:aws:iam::123456789012:user/David

        <!-- Amazon RDS instance used for tagging -->
        arn:aws:rds:eu-west-1:123456789012:db:mysql-db

        <!-- Object in an Amazon S3 bucket -->
        arn:aws:s3:::my_corporate_bucket/exampleobject.png

    """

    arn_regex = re.compile(r'^arn:(?P<partition>\w+):(?P<service>\w+):'
                           r'(?P<region>\w+(?:-\w+)+)?:'
                           r'(?P<account_id>\d{12})?:(?P<resource_type>[^:/]+)'
                           r'(?P<resource_separator>[:/])?(?P<resource>.*)')

    partition = None
    service = None
    region = None
    account_id = None
    resource_type = None
    resource_separator = None
    resource = None

    def __init__(self, arn):
        """
        Parse ARN string into its component pieces.

        Args:
            arn (str): Amazon Resource Name

        """
        self.arn = arn
        match = self.arn_regex.match(arn)

        if not match:
            raise InvalidArn('Invalid ARN: {0}'.format(arn))

        for key, val in match.groupdict().items():
            setattr(self, key, val)

    def __repr__(self):
        """Return the ARN itself."""
        return self.arn


def _get_primary_account_id():
    """Return the account ID for the primary AWS account."""
    return boto3.client('sts').get_caller_identity().get('Account')


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
    awsarn = AwsArn(arn)
    response = sts.assume_role(
        Policy=json.dumps(cloudigrade_policy),
        RoleArn='{0}'.format(awsarn),
        RoleSessionName='cloudigrade-{0}'.format(awsarn.account_id)
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
        logger.debug(_('Describing instances in {0}').format(region_name))
        instances = ec2.describe_instances()
        for reservation in instances.get('Reservations', []):
            running_instances[region_name] = [
                instance for instance in reservation.get('Instances', [])
                if InstanceState.is_running(instance['State']['Code'])
            ]

    return running_instances


def get_ec2_instance(session, instance_id):
    """
    Return an EC2 AwsInstance object from the customer account.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        instance_id (str): An EC2 instance ID

    Returns:
        AwsInstance: A boto3 AwsInstance object.

    """
    return session.resource('ec2').Instance(instance_id)


def get_ami(session, image_id, region):
    """
    Return an Amazon Machine Image running on an EC2 instance.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        image_id (str): An AMI ID

    Returns:
        Image: A boto3 EC2 Image object.

    """
    return session.resource('ec2', region_name=region).Image(image_id)


def get_ami_snapshot_id(ami):
    """
    Return the snapshot id from an Image object.

    Args:
        ami (boto3.resources.factory.ec2.Image): A machine image object

    Returns:
        string: The snapshot id for the machine image's root volume

    """
    for mapping in ami.block_device_mappings:
        # For now we are focusing exclusively on the root device
        if mapping['DeviceName'] != ami.root_device_name:
            continue
        return mapping.get('Ebs', {}).get('SnapshotId', '')


def get_snapshot(session, snapshot_id, region):
    """
    Return an AMI Snapshot for an EC2 instance.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        snapshot_id (str): A snapshot ID

    Returns:
        Snapshot: A boto3 EC2 Snapshot object.

    """
    return session.resource('ec2', region_name=region).Snapshot(snapshot_id)


def add_snapshot_ownership(session, snapshot, region):
    """
    Addpermissions to a snapshot.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        snapshot_id (str): The id of the snapshot to modify
        region (str): The region the machine image and snapshot reside in

    Returns:
        None

    Raises:
        AwsSnapshotNotOwnedError: Ownership was not verified.

    """
    attribute = 'createVolumePermission'
    user_id = _get_primary_account_id()

    permission = {
        'Add': [
            {'UserId': user_id},
        ]
    }

    snapshot.modify_attribute(
        Attribute=attribute,
        CreateVolumePermission=permission,
        OperationType='add',
        UserIds=[user_id]
    )

    # The modify call returns None. This is a check to make sure
    # permissions are added successfully.
    response = snapshot.describe_attribute(Attribute='createVolumePermission')

    for user in response['CreateVolumePermissions']:
        if user['UserId'] == user_id:
            return

    message = _('No CreateVolumePermissions on Snapshot {0} for UserId {1}').\
        format(snapshot.snapshot_id, user_id)
    raise AwsSnapshotNotOwnedError(message)


def copy_snapshot(snapshot_id, source_region):
    """
    Copy a machine image snapshot to a primary AWS account.

    Note: This operation is done from the primarmy account.

    Args:
        snapshot_id (str): The id of the snapshot to modify
        source_region (str): The region the source snapshot resides in

    Returns:
        str: The id of the newly copied snapshot

    """
    snapshot = boto3.resource('ec2').Snapshot(snapshot_id)
    try:
        response = snapshot.copy(SourceRegion=source_region)
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceLimitExceeded':
            raise AwsSnapshotCopyLimitError(e.response['Error']['Message'])
        else:
            raise e
    else:
        return response.get('SnapshotId')


def create_volume(snapshot_id, zone):
    """
    Create a volume on the primary AWS account for the given snapshot.

    Args:
        snapshot_id (str): The id of the snapshot to use for the volume
        zone (str): The availability zone in which to create the volume

    Returns:
        str: The id of the newly created volume

    """
    ec2 = boto3.resource('ec2')
    snapshot = ec2.Snapshot(snapshot_id)
    if snapshot.state != 'completed':
        message = '{0} {1} {2}'.format(snapshot_id,
                                       snapshot.state,
                                       snapshot.progress)
        raise SnapshotNotReadyException(message)
    volume = ec2.create_volume(SnapshotId=snapshot_id, AvailabilityZone=zone)
    return volume.id


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


def _handle_dry_run_response_exception(action, e):
    """
    Handle the normal exception that is raised from a dry-run operation.

    This may look weird, but when a boto3 operation is executed with the
    ``DryRun=True`` argument, the typical behavior is for it to raise a
    ``ClientError`` exception with an error code buried within to indicate if
    the operation would have succeeded.

    See also:
        https://botocore.readthedocs.io/en/latest/client_upgrades.html#error-handling

    Args:
        action (str): The action that was attempted
        e (botocore.exceptions.ClientError): The raised exception

    Returns:
        bool: Whether the operation had access verified, or not.

    """
    dry_run_operation = 'DryRunOperation'
    unauthorized_operation = 'UnauthorizedOperation'

    if e.response['Error']['Code'] == dry_run_operation:
        logger.debug(_('Verified access to "{0}"').format(action))
        return True
    elif e.response['Error']['Code'] == unauthorized_operation:
        logger.warning(_('No access to "{0}"').format(action))
        return False
    raise e


def _verify_policy_action(session, action):
    """
    Check to see if we have access to a specific action.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        action (str): The policy action to check

    Returns:
        bool: Whether the action is allowed, or not.

    """
    ec2 = session.client('ec2')

    try:
        if action == 'ec2:DescribeImages':
            ec2.describe_images(DryRun=True)
        elif action == 'ec2:DescribeInstances':
            ec2.describe_instances(DryRun=True)
        elif action == 'ec2:DescribeSnapshotAttribute':
            ec2.describe_snapshot_attribute(
                DryRun=True,
                SnapshotId=SNAPSHOT_ID,
                Attribute='productCodes'
            )
        elif action == 'ec2:DescribeSnapshots':
            ec2.describe_snapshots(DryRun=True)
        elif action == 'ec2:ModifySnapshotAttribute':
            ec2.modify_snapshot_attribute(
                SnapshotId=SNAPSHOT_ID,
                DryRun=True,
                Attribute='createVolumePermission',
                OperationType='add',
            )
        elif action == 'ec2:ModifyImageAttribute':
            ec2.modify_image_attribute(
                Attribute='description',
                ImageId='string',
                DryRun=True
            )
        else:
            logger.warning(_('No test case exists for action "{0}"')
                           .format(action))
            return False
    except ClientError as e:
        return _handle_dry_run_response_exception(action, e)


def receive_message_from_queue(queue_url):
    """
    Get message objects from SQS Queue object.

    Args:
        queue_url (str): The AWS assigned URL for the queue.

    Returns:
        list[Message]: A list of message objects.

    """
    region = settings.SQS_DEFAULT_REGION
    sqs_queue = boto3.resource('sqs', region_name=region).Queue(queue_url)

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
    region = settings.SQS_DEFAULT_REGION
    sqs_queue = boto3.resource('sqs', region_name=region).Queue(queue_url)

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
    region = settings.S3_DEFAULT_REGION
    s3_object = boto3.resource('s3', region_name=region).Object(bucket, key)

    object_bytes = s3_object.get()['Body'].read()

    if compression == 'gzip':
        content = gzip.decompress(object_bytes).decode('utf-8')
    elif compression is None:
        content = object_bytes.decode('utf-8')
    else:
        logger.error(_('Unsupported compression format'))

    return content


def extract_sqs_message(message, service='s3'):
    """
    Parse SQS message for service-specific content.

    Args:
        message (boto3.SQS.Message): The Message object.
        service (str): The AWS service the message refers to.

    Returns:
        list(dict): List of message records.

    """
    extracted_records = []
    message_body = json.loads(message.body)
    for record in message_body.get('Records', []):
        extracted_records.append(record[service])
    return extracted_records


def rewrap_aws_errors(original_function):
    """
    Decorate function to except boto AWS ClientError and raise as RuntimeError.

    This is useful when we have boto calls inside of Celery tasks but Celery
    cannot serialize boto AWS ClientError using JSON. If we encounter other
    boto/AWS-specific exceptions that are not serializable, we should add
    support for them here.

    Args:
        original_function: The function to decorate.

    Returns:
        function: The decorated function.

    """
    @wraps(original_function)
    def wrapped(*args, **kwargs):
        try:
            result = original_function(*args, **kwargs)
        except ClientError as e:
            message = _('Unexpected AWS error {0}: {1}').format(type(e), e)
            raise RuntimeError(message)
        return result
    return wrapped
