"""Helper functions for generating test data."""
import random
import uuid

from account.models import AwsAccount, AwsInstance, InstanceEvent, \
    AwsInstanceEvent
from util import aws
from util.tests import helper

AWS_PROVIDER_STRING = 'aws'


def generate_aws_account(arn=None, aws_account_id=None):
    """
    Generate an AwsAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        arn (str): Optional ARN.
        aws_account_id (decimal.Decimal): Optional AWS account ID.

    Returns:
        AwsAccount: The created AwsAccount.

    """
    if arn is None:
        arn = helper.generate_dummy_arn(aws_account_id)
    if aws_account_id is None:
        aws_account_id = aws.extract_account_id_from_arn(arn)

    return AwsAccount.objects.create(
        account_arn=arn,
        aws_account_id=aws_account_id,
    )


def generate_aws_instance(account, ec2_instance_id=None, region=None):
    """
    Generate an AwsInstance for the AwsAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        account (AwsAccount): Account that owns the instance.
        ec2_instance_id (str): Optional EC2 instance id.
        region (str): Optional AWS region where the instance runs.

    Returns:
        AwsInstance: The created AwsInstance.

    """
    if ec2_instance_id is None:
        ec2_instance_id = str(uuid.uuid4())
    if region is None:
        region = random.choice(helper.SOME_AWS_REGIONS)

    return AwsInstance.objects.create(
        account=account,
        ec2_instance_id=ec2_instance_id,
        region=region,
    )


def generate_aws_instance_events(
    instance, powered_times, ec2_ami_id=None, instance_type=None, subnet=None
):
    """
    Generate list of AwsInstanceEvents for the AwsInstance for testing.

    Any optional arguments not provided will be randomly generated.

    The ``powered_times`` defines when the instance should be considered
    running for sake of the event types. The first element of the tuple
    is a datetime.datetime of when a "power on" event occurs, and the second
    element is a datetime.datetime of when a "power off" event occurs.

    Args:
        instance (AwsInstance): instance that owns the events.
        powered_times (list[tuple]): Time periods the instance is powered on.
        ec2_ami_id (str): Optional EC2 AMI ID the instance runs.
        instance_type (str): Optional AWS instance type.
        subnet (str): Optional subnet ID where instance runs.

    Returns:
        list(AwsInstanceEvent): The list of created AwsInstanceEvents.

    """
    if ec2_ami_id is None:
        ec2_ami_id = str(uuid.uuid4())
    if instance_type is None:
        instance_type = random.choice(helper.SOME_EC2_INSTANCE_TYPES)
    if subnet is None:
        subnet = str(uuid.uuid4())

    events = []
    for power_on_time, power_off_time in powered_times:
        if power_on_time is not None:
            event = AwsInstanceEvent.objects.create(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=power_on_time,
                subnet=subnet,
                ec2_ami_id=ec2_ami_id,
                instance_type=instance_type,
            )
            events.append(event)
        if power_off_time is not None:
            event = AwsInstanceEvent.objects.create(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_off,
                occurred_at=power_off_time,
                subnet=subnet,
                ec2_ami_id=ec2_ami_id,
                instance_type=instance_type,
            )
            events.append(event)
    return events
