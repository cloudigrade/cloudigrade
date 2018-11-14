"""Helper functions for generating test data."""
import json
import random
import uuid

import faker
from django.conf import settings

from account.models import (AwsAccount, AwsEC2InstanceDefinitions, AwsInstance,
                            AwsInstanceEvent, AwsMachineImage,
                            CLOUD_ACCESS_NAME_TOKEN, InstanceEvent,
                            MARKETPLACE_NAME_TOKEN, MachineImage)
from util import aws
from util.tests import helper

_faker = faker.Faker()


def generate_aws_account(arn=None, aws_account_id=None, user=None, name=None,
                         created_at=None):
    """
    Generate an AwsAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        arn (str): Optional ARN.
        aws_account_id (12-digit string): Optional AWS account ID.
        user (User): Optional Django auth User to be this account's owner.
        name (str): Optional name for this account.
        created_at (datetime): Optional creation datetime for this account.

    Returns:
        AwsAccount: The created AwsAccount.

    """
    if arn is None:
        arn = helper.generate_dummy_arn(account_id=aws_account_id)

    if user is None:
        user = helper.generate_test_user()

    if name is None:
        name = str(uuid.uuid4())

    account = AwsAccount.objects.create(
        account_arn=arn,
        aws_account_id=aws.AwsArn(arn).account_id,
        user=user,
        name=name,
    )
    if created_at:
        account.created_at = created_at
        account.save()
    return account


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
        ec2_instance_id = helper.generate_dummy_instance_id()
    if region is None:
        region = random.choice(helper.SOME_AWS_REGIONS)

    return AwsInstance.objects.create(
        account=account,
        ec2_instance_id=ec2_instance_id,
        region=region,
    )


def generate_single_aws_instance_event(
        instance, powered_time=None, event_type=None, ec2_ami_id=None,
        instance_type=None, subnet=None, no_image=False):
    """
    Generate single AwsInstanceEvent for testing.

    The ``powered_time`` is a datetime.datetime that defines when
    the instance event (either powering on or powering off) occurred.

    Args:
        instance (AwsInstance): instance that owns the events.
        powered_time (datetime): Time that the instance is powered on.
        event_type (str): AWS event type
        ec2_ami_id (str): Optional EC2 AMI ID the instance runs.
        instance_type (str): Optional AWS instance type.
        subnet (str): Optional subnet ID where instance runs.
        no_image (bool): If true, don't create and assign an image.

    Returns:
        AwsInstanceEvent: The created AwsInstanceEvent.

    """
    if instance_type is None:
        instance_type = random.choice(tuple(
            helper.SOME_EC2_INSTANCE_TYPES.keys()
        ))
    if subnet is None:
        subnet = helper.generate_dummy_subnet_id()
    if event_type is None:
        event_type = InstanceEvent.TYPE.power_off

    image = None
    if not no_image:
        if ec2_ami_id is None:
            ec2_ami_id = helper.generate_dummy_image_id()
        image, __ = AwsMachineImage.objects.get_or_create(
            ec2_ami_id=ec2_ami_id,
            defaults={
                'owner_aws_account_id': instance.account.aws_account_id,
            }
        )

    event = AwsInstanceEvent.objects.create(
        instance=instance,
        machineimage=image,
        event_type=event_type,
        occurred_at=powered_time,
        subnet=subnet,
        instance_type=instance_type,
    )
    return event


def generate_aws_instance_events(
    instance, powered_times, ec2_ami_id=None, instance_type=None, subnet=None,
    no_image=False,
):
    """
    Generate list of AwsInstanceEvents for the AwsInstance for testing.

    Any optional arguments not provided will be randomly generated.

    The ``powered_times`` defines when the instance should be considered
    running for sake of the event types. The first element of the tuple
    is a datetime.datetime of when a "power on" event occurs, and the second
    element is a datetime.datetime of when a "power off" event occurs.

    Power-off events will never be created with an image defined in this helper
    function because in most real-world cases they do not have one.

    Args:
        instance (AwsInstance): instance that owns the events.
        powered_times (list[tuple]): Time periods the instance is powered on.
        ec2_ami_id (str): Optional EC2 AMI ID the instance runs.
        instance_type (str): Optional AWS instance type.
        subnet (str): Optional subnet ID where instance runs.
        no_image (bool): If true, don't assign an image.

    Returns:
        list(AwsInstanceEvent): The list of created AwsInstanceEvents.

    """
    if no_image:
        ec2_ami_id = None
    elif ec2_ami_id is None:
        ec2_ami_id = helper.generate_dummy_image_id()
    if instance_type is None:
        instance_type = random.choice(tuple(
            helper.SOME_EC2_INSTANCE_TYPES.keys()
        ))
    if subnet is None:
        subnet = helper.generate_dummy_subnet_id()

    events = []
    for power_on_time, power_off_time in powered_times:
        if power_on_time is not None:
            event = generate_single_aws_instance_event(
                instance=instance,
                powered_time=power_on_time,
                event_type=InstanceEvent.TYPE.power_on,
                ec2_ami_id=ec2_ami_id,
                instance_type=instance_type,
                subnet=subnet,
                no_image=no_image
            )
            events.append(event)
        if power_off_time is not None:
            # power_off events typically do *not* have an image defined.
            # So, ignore inputs and *always* set ec2_ami_id=None.
            event = generate_single_aws_instance_event(
                instance=instance,
                powered_time=power_off_time,
                event_type=InstanceEvent.TYPE.power_off,
                ec2_ami_id=None,
                instance_type=instance_type,
                subnet=subnet,
                no_image=True
            )
            events.append(event)
    return events


def generate_aws_image(owner_aws_account_id=None,
                       is_encrypted=False,
                       is_windows=False,
                       ec2_ami_id=None,
                       rhel_detected=False,
                       openshift_detected=False,
                       name=None,
                       status=MachineImage.INSPECTED,
                       rhel_challenged=False,
                       openshift_challenged=False,
                       is_cloud_access=False,
                       is_marketplace=False):
    """
    Generate an AwsMachineImage.

    Any optional arguments not provided will be randomly generated.

    Args:
        owner_aws_account_id (int): Optional AWS account that owns the image.
        is_encrypted (bool): Optional Indicates if image is encrypted.
        is_windows (bool): Optional Indicates if AMI is Windows.
        ec2_ami_id (str): Optional EC2 AMI ID of the image
        rhel_detected (bool): Optional Indicates if RHEL is detected.
        openshift_detected (bool): Optional Indicates if OpenShift is detected.
        name (str): Optional AMI name.
        status (str): Optional MachineImage inspection status.
        rhel_challenged (bool): Optional indicates if RHEL is challenged.
        openshift_challenged (bool): Optional indicates if OCP is challenged.
        is_cloud_access (bool): Optional indicates if image is from Cloud
            Access. Has side-effect of modifying the owner_aws_account_id and
            name as appropriate.
        is_marketplace (bool): Optional indicates if image is from Marketplace.
            Has side-effect of modifying the owner_aws_account_id and name as
            appropriate.

    Returns:
        AwsMachineImage: The created AwsMachineImage.

    """
    if not owner_aws_account_id:
        owner_aws_account_id = helper.generate_dummy_aws_account_id()
    if not ec2_ami_id:
        ec2_ami_id = helper.generate_dummy_image_id()
    platform = AwsMachineImage.WINDOWS if is_windows else AwsMachineImage.NONE

    if rhel_detected:
        image_json = json.dumps({'rhel_release_files_found': rhel_detected})
    else:
        image_json = None

    if is_marketplace:
        name = f'{name or _faker.name()}{MARKETPLACE_NAME_TOKEN}'
        owner_aws_account_id = random.choice(settings.RHEL_IMAGES_AWS_ACCOUNTS)

    if is_cloud_access:
        name = f'{name or _faker.name()}{CLOUD_ACCESS_NAME_TOKEN}'
        owner_aws_account_id = random.choice(settings.RHEL_IMAGES_AWS_ACCOUNTS)

    image = AwsMachineImage.objects.create(
        owner_aws_account_id=owner_aws_account_id,
        ec2_ami_id=ec2_ami_id,
        is_encrypted=is_encrypted,
        inspection_json=image_json,
        openshift_detected=openshift_detected,
        platform=platform,
        name=name,
        status=status,
        rhel_challenged=rhel_challenged,
        openshift_challenged=openshift_challenged
    )
    return image


def generate_aws_ec2_definitions():
    """Generate all defined AwsEC2InstanceDefinitions."""
    instance_types = helper.SOME_EC2_INSTANCE_TYPES

    for name, instance in instance_types.items():
        AwsEC2InstanceDefinitions.objects.create(
            instance_type=name,
            memory=instance['memory'],
            vcpu=instance['vcpu']
        )
