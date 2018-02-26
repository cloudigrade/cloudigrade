"""Helper functions for generating test data."""
import random
import uuid

from account.models import Account, Instance, InstanceEvent
from util import aws
from util.tests import helper


def generate_account(arn=None, account_id=None):
    """
    Generate an Account for testing for random ARN and AWS Account ID.

    Args:
        arn (str): Optional ARN for the Account.
        account_id (decimal.Decimal): Optional AWS Account ID.

    Returns:
        Account: The created Account.

    """
    if arn is None:
        arn = helper.generate_dummy_arn(account_id)
    if account_id is None:
        account_id = aws.extract_account_id_from_arn(arn)

    return Account(account_arn=arn, account_id=account_id)


def generate_instance(account, ec2_instance_id=None, region=None):
    """
    Generate an Instance for the Account for testing with random attributes.

    Args:
        account (Account): Account that owns the Instance.
        ec2_instance_id (str): Optional EC2 Instance ID.
        region (str): Optional AWS region where the Instance runs.

    Returns:
        Instance: The created Instance.

    """
    if ec2_instance_id is None:
        ec2_instance_id = str(uuid.uuid4())
    if region is None:
        region = random.choice(helper.SOME_AWS_REGIONS)

    return Instance(
        account=account,
        ec2_instance_id=ec2_instance_id,
        region=region
    )


def generate_instance_events(instance, powered_times, ec2_ami_id=None,
                             instance_type=None, subnet=None):
    """
    Generate list of InstanceEvents for the Instance for testing.

    The ``powered_times`` defines when the Instance should be considered
    running for sake of the event types. The first element of the tuple
    is a datetime.datetime of when a "power on" event occurs, and the second
    element is a datetime.datetime of when a "power off" event occurs.

    Args:
        instance (account.models.Instance): Instance that owns the events.
        powered_times (list[tuple]): Time periods the Instance is powered on.
        ec2_ami_id (str): Optional EC2 AMI ID the Instance runs.
        instance_type (str): Optional AWS Instance Type.
        subnet (str): Optional subnet ID where Instance runs.

    Returns:
        list(InstanceEvent): The list of created InstanceEvents.

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
            event = InstanceEvent(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_on,
                occurred_at=power_on_time,
                subnet=subnet,
                ec2_ami_id=ec2_ami_id,
                instance_type=instance_type,
            )
            events.append(event)
        if power_off_time is not None:
            event = InstanceEvent(
                instance=instance,
                event_type=InstanceEvent.TYPE.power_off,
                occurred_at=power_off_time,
                subnet=subnet,
                ec2_ami_id=ec2_ami_id,
                instance_type=instance_type,
            )
            events.append(event)
    return events
