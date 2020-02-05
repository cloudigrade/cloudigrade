"""Helper functions for generating test data."""
import functools
import json
import logging
import random
import uuid
from unittest.mock import patch

import faker
from django.conf import settings
from rest_framework.test import APIClient

from api.clouds.aws import tasks
from api.clouds.aws.cloudtrail import CloudTrailInstanceEvent
from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsEC2InstanceDefinition,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    CLOUD_ACCESS_NAME_TOKEN,
    MARKETPLACE_NAME_TOKEN,
)
from api.models import (
    CloudAccount,
    Instance,
    InstanceEvent,
    MachineImage,
    Run,
)
from api.util import (
    calculate_max_concurrent_usage_from_runs,
    recalculate_runs,
)
from util import aws
from util.aws.sqs import _sqs_wrap_message
from util.tests import helper

_faker = faker.Faker()
logger = logging.getLogger(__name__)


class SandboxedRestClient(object):
    """
    Very special REST client intended only for local sandbox testing.

    This client short-circuits some otherwise important behaviors so we don't
    make calls to the real public clouds when interacting with objects. These
    short-circuited behaviors all simulate "happy path" responses from the
    public clouds.

    This client can be useful for testing the general interaction and output of
    our APIs when we do not expect or need to override specific responses from
    the real public clouds.
    """

    def __init__(self):
        """Initialize the client."""
        self.client = APIClient()
        self.authenticated_user = None
        self.bypass_aws_calls = True
        self.aws_account_verified = True
        self.aws_primary_account_id = int(helper.generate_dummy_aws_account_id())

    def _call_api(self, verb, path, data=None):
        """
        Make the simulated API call, optionally patching cloud interactions.

        If `self.bypass_aws_calls` is True, the following objects are patched
        so we remain more truly "sandboxed" for the call:

        - aws.verify_account_access is used in account creation
        - aws.sts.boto3 is used in account creation
        - aws.disable_cloudtrail is used in account deletion
        - aws.get_session is used in account deletion
        - aws.sts._get_primary_account_id is used in sysconfig
        - tasks.initial_aws_describe_instances is used in account creation

        Returns:
            rest_framework.response.Response

        """
        if self.bypass_aws_calls:
            with patch.object(
                aws, "verify_account_access"
            ) as mock_verify, patch.object(aws.sts, "boto3"), patch.object(
                aws, "disable_cloudtrail"
            ), patch.object(
                aws, "get_session"
            ), patch.object(
                aws.sts, "_get_primary_account_id"
            ) as mock_get_primary_account_id, patch.object(
                tasks, "initial_aws_describe_instances"
            ):
                mock_verify.return_value = self.aws_account_verified, []
                mock_get_primary_account_id.return_value = self.aws_primary_account_id
                response = getattr(self.client, verb)(path, data=data)
        else:
            response = getattr(self.client, verb)(path, data=data)
        return response

    def __getattr__(self, item):
        """
        Get an appropriate RESTful API-calling method.

        If we want to customize any specific API's behavior, we can simply add
        a new method to this class following the "verb_noun" pattern. For
        example, "create_account" would handle POSTs to the account API.
        """
        try:
            verb, noun = item.split("_")
            if verb == "list":
                verb = "get"
            elif verb == "create":
                verb = "post"
            return functools.partial(self.verb_noun, verb, noun)
        except Exception:
            raise AttributeError(
                f"'{self.__class__.__name__}' object " f"has no attribute '{item}'"
            )

    def _force_authenticate(self, user):
        """Force client authentication as the given user."""
        self.authenticated_user = user
        self.client.credentials(
            HTTP_X_RH_IDENTITY=helper.get_3scale_auth_header(user.username)
        )

    def verb_noun(
        self, verb, noun, noun_id=None, detail=None, data=None, api_root="/v2"
    ):
        """Make a simulated REST API call for the given inputs."""
        if detail:
            path = f"{api_root}/{noun}/{noun_id}/{detail}/"
        elif noun_id:
            path = f"{api_root}/{noun}/{noun_id}/"
        elif verb == "report":
            path = f"{api_root}/report/{noun}/"
            verb = "get"
        else:
            path = f"{api_root}/{noun}/"
        return self._call_api(verb=verb, path=path, data=data)


def generate_aws_account(
    arn=None,
    aws_account_id=None,
    user=None,
    name=None,
    created_at=None,
    aws_access_key_id=None,
):
    """
    Generate an AwsAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        arn (str): Optional ARN.
        aws_account_id (12-digit string): Optional AWS account ID.
        user (User): Optional Django auth User to be this account's owner.
        name (str): Optional name for this account.
        created_at (datetime): Optional creation datetime for this account.
        aws_access_key_id (str): Optional aws_access_key_id.

    Returns:
        CloudAccount: The created AwsAccount.

    """
    if arn is None:
        arn = helper.generate_dummy_arn(account_id=aws_account_id)

    if user is None:
        user = helper.generate_test_user()

    if name is None:
        name = str(uuid.uuid4())

    if aws_access_key_id is None:
        aws_access_key_id = _faker.user_name()

    aws_cloud_account = AwsCloudAccount.objects.create(
        account_arn=arn,
        aws_account_id=aws.AwsArn(arn).account_id,
        aws_access_key_id=aws_access_key_id,
    )
    if created_at:
        aws_cloud_account.created_at = created_at
        aws_cloud_account.save()
    cloud_account = CloudAccount.objects.create(
        user=user, name=name, content_object=aws_cloud_account,
    )
    if created_at:
        cloud_account.created_at = created_at
        cloud_account.save()

    return cloud_account


def generate_aws_instance(
    cloud_account, ec2_instance_id=None, region=None, image=None, no_image=False
):
    """
    Generate an AwsInstance for the AwsAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        cloud_account (CloudAccount): Account that owns the instance.
        ec2_instance_id (str): Optional EC2 instance id.
        region (str): Optional AWS region where the instance runs.
        image (MachineImage): Optional image to add instead of creating one.
        no_image (bool): Whether an image should be attached to this instance.

    Returns:
        Instance: The created AwsInstance.

    """
    if ec2_instance_id is None:
        ec2_instance_id = helper.generate_dummy_instance_id()
    if region is None:
        region = helper.get_random_region()
    if image is None:
        if not no_image:
            ec2_ami_id = helper.generate_dummy_image_id()

            aws_image, created = AwsMachineImage.objects.get_or_create(
                ec2_ami_id=ec2_ami_id,
                defaults={
                    "owner_aws_account_id": cloud_account.content_object.aws_account_id,
                },
            )
            if created:
                image = MachineImage.objects.create(content_object=aws_image,)
            else:
                image = aws_image.machine_image.get()

    aws_instance = AwsInstance.objects.create(
        ec2_instance_id=ec2_instance_id, region=region,
    )
    instance = Instance.objects.create(
        cloud_account=cloud_account, content_object=aws_instance, machine_image=image
    )

    return instance


def generate_single_aws_instance_event(
    instance,
    occurred_at,
    event_type=None,
    instance_type=None,
    subnet=None,
    no_instance_type=False,
    no_subnet=False,
):
    """
    Generate single AwsInstanceEvent for testing.

    The ``powered_time`` is a datetime.datetime that defines when
    the instance event (either powering on or powering off) occurred.

    Args:
        instance (Instance): instance that owns the events.
        occurred_at (datetime.datetime): Time that the instance occurred.
        event_type (str): AWS event type
        instance_type (str): Optional AWS instance type.
        subnet (str): Optional subnet ID where instance runs.
        no_instance_type (bool): If true, don't assign an instance type.
        no_subnet (bool): If true, don't create and assign a subnet.

    Returns:
        AwsInstanceEvent: The created AwsInstanceEvent.

    """
    if no_instance_type:
        instance_type = None
    elif instance_type is None:
        instance_type = helper.get_random_instance_type()

    if no_subnet:
        subnet = None
    elif subnet is None:
        subnet = helper.generate_dummy_subnet_id()

    if event_type is None:
        event_type = InstanceEvent.TYPE.power_off

    aws_event = AwsInstanceEvent.objects.create(
        subnet=subnet, instance_type=instance_type,
    )
    event = InstanceEvent.objects.create(
        instance=instance,
        event_type=event_type,
        occurred_at=occurred_at,
        content_object=aws_event,
    )
    return event


def generate_aws_instance_events(
    instance, powered_times, instance_type=None, subnet=None, no_instance_type=False
):
    """
    Generate list of InstanceEvents for the Instance for testing.

    Any optional arguments not provided will be randomly generated.

    The ``powered_times`` defines when the instance should be considered
    running for sake of the event types. The first element of the tuple
    is a datetime.datetime of when a "power on" event occurs, and the second
    element is a datetime.datetime of when a "power off" event occurs.

    Power-off events will never be created with an image defined in this helper
    function because in most real-world cases they do not have one.

    Args:
        instance (Instance): instance that owns the events.
        powered_times (list[tuple]): Time periods the instance is powered on.
        instance_type (str): Optional AWS instance type.
        subnet (str): Optional subnet ID where instance runs.
        no_instance_type (bool): If true, instance_type is not set

    Returns:
        list(InstanceEvent): The list of created AwsInstanceEvents.

    """
    if no_instance_type:
        instance_type = None
    elif instance_type is None:
        instance_type = helper.get_random_instance_type()
    if subnet is None:
        subnet = helper.generate_dummy_subnet_id()

    events = []
    for power_on_time, power_off_time in powered_times:
        if power_on_time is not None:
            event = generate_single_aws_instance_event(
                instance=instance,
                occurred_at=power_on_time,
                event_type=InstanceEvent.TYPE.power_on,
                instance_type=instance_type,
                subnet=subnet,
                no_instance_type=no_instance_type,
            )
            events.append(event)
        if power_off_time is not None:
            # power_off events typically do *not* have an image defined.
            # So, ignore inputs and *always* set ec2_ami_id=None.
            event = generate_single_aws_instance_event(
                instance=instance,
                occurred_at=power_off_time,
                event_type=InstanceEvent.TYPE.power_off,
                instance_type=instance_type,
                subnet=subnet,
                no_instance_type=no_instance_type,
            )
            events.append(event)
    return events


def generate_cloudtrail_instance_event(
    instance,
    occurred_at,
    event_type=None,
    instance_type=None,
    subnet=None,
    no_instance_type=False,
    no_subnet=False,
):
    """
    Generate a single CloudTrailInstanceEvent for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        instance (Instance): instance that owns the events.
        occurred_at (datetime): Time periods the instance is powered on.
        instance_type (str): Optional AWS instance type.
        subnet (str): Optional subnet ID where instance runs.
        no_instance_type (bool): If true, instance_type is not set

    Returns:
        CloudTrailInstanceEvent: The created CloudTrailInstanceEvent.

    """
    if no_instance_type:
        instance_type = None
    elif instance_type is None:
        instance_type = helper.get_random_instance_type()

    if no_subnet:
        subnet = None
    elif subnet is None:
        subnet = helper.generate_dummy_subnet_id()

    if event_type is None:
        event_type = InstanceEvent.TYPE.power_off

    event = CloudTrailInstanceEvent(
        occurred_at=occurred_at,
        event_type=event_type,
        instance_type=instance_type,
        aws_account_id=instance.cloud_account.id,
        region=instance.machine_image.content_object.region,
        ec2_instance_id=instance.content_object.ec2_instance_id,
        ec2_ami_id=instance.machine_image.content_object.ec2_ami_id,
        subnet_id=subnet,
    )
    return event


def generate_aws_image(
    owner_aws_account_id=None,
    is_encrypted=False,
    is_windows=False,
    ec2_ami_id=None,
    rhel_detected=False,
    rhel_detected_by_tag=False,
    rhel_detected_repos=False,
    rhel_detected_certs=False,
    rhel_detected_release_files=False,
    rhel_detected_signed_packages=False,
    rhel_version=None,
    syspurpose=None,
    openshift_detected=False,
    name=None,
    status=MachineImage.INSPECTED,
    is_cloud_access=False,
    is_marketplace=False,
):
    """
    Generate an AwsMachineImage.

    Any optional arguments not provided will be randomly generated.

    Args:
        owner_aws_account_id (int): Optional AWS account that owns the image.
        is_encrypted (bool): Optional Indicates if image is encrypted.
        is_windows (bool): Optional Indicates if AMI is Windows.
        ec2_ami_id (str): Optional EC2 AMI ID of the image
        rhel_detected (bool): Optional Indicates if RHEL is detected.
        rhel_detected_by_tag (bool): Optional indicates if RHEL is detected by tag.
        rhel_detected_repos (bool): Optional indicates if RHEL is detected via
            enabled yum repos.
        rhel_detected_certs (bool): Optional indicates if RHEL is detected via
            product certificates.
        rhel_detected_release_files (bool): Optional indicates if RHEL is
            detected via release files.
        rhel_detected_signed_packages (bool): Optional indicates if RHEL is
            detected via signed packages.
        rhel_version (str): Optional indicates what RHEL version is detected.
        syspurpose (dict): Optional indicates what syspurpose is detected.
        openshift_detected (bool): Optional Indicates if OpenShift is detected.
        name (str): Optional AMI name.
        status (str): Optional MachineImage inspection status.
        is_cloud_access (bool): Optional indicates if image is from Cloud
            Access. Has side-effect of modifying the owner_aws_account_id and
            name as appropriate.
        is_marketplace (bool): Optional indicates if image is from Marketplace.
            Has side-effect of modifying the owner_aws_account_id and name as
            appropriate.

    Returns:
        MachineImage: The created AwsMachineImage.

    """
    if not owner_aws_account_id:
        owner_aws_account_id = helper.generate_dummy_aws_account_id()
    if not ec2_ami_id:
        ec2_ami_id = helper.generate_dummy_image_id()
    platform = AwsMachineImage.WINDOWS if is_windows else AwsMachineImage.NONE

    if rhel_detected:
        if not any(
            (
                rhel_detected_certs,
                rhel_detected_release_files,
                rhel_detected_repos,
                rhel_detected_signed_packages,
            )
        ):
            image_json = json.dumps({"rhel_release_files_found": rhel_detected})
        else:
            image_json = json.dumps(
                {
                    "rhel_enabled_repos_found": rhel_detected_repos,
                    "rhel_product_certs_found": rhel_detected_certs,
                    "rhel_release_files_found": rhel_detected_release_files,
                    "rhel_signed_packages_found": rhel_detected_signed_packages,
                    "rhel_version": rhel_version,
                    "syspurpose": syspurpose,
                }
            )
    else:
        image_json = None

    if is_marketplace:
        name = f"{name or _faker.name()}{MARKETPLACE_NAME_TOKEN}"
        owner_aws_account_id = random.choice(settings.RHEL_IMAGES_AWS_ACCOUNTS)

    if is_cloud_access:
        name = f"{name or _faker.name()}{CLOUD_ACCESS_NAME_TOKEN}"
        owner_aws_account_id = random.choice(settings.RHEL_IMAGES_AWS_ACCOUNTS)

    aws_machine_image = AwsMachineImage.objects.create(
        owner_aws_account_id=owner_aws_account_id,
        ec2_ami_id=ec2_ami_id,
        platform=platform,
    )
    machine_image = MachineImage.objects.create(
        is_encrypted=is_encrypted,
        inspection_json=image_json,
        rhel_detected_by_tag=rhel_detected_by_tag,
        openshift_detected=openshift_detected,
        name=name,
        status=status,
        content_object=aws_machine_image,
    )

    return machine_image


def generate_single_run(
    instance,
    runtime,
    image=None,
    no_image=False,
    instance_type=None,
    no_instance_type=False,
    calculate_concurrent_usage=True,
):
    """
    Generate a single Run (and related events) for testing.

    Args:
        instance (Instance): instance that was ran.
        runtime (tuple(datetime.datetime, datetime.datetime)):
            time the run occured.
        image (Image): image that was ran.
        no_image (bool): If true, don't create and assign an image.
        instance_type (str): Optional AWS instance type.
        no_instance_type (bool): Optional indication that instance has no type.
        calculate_concurrent_usage (bool): Optional indicated if after creating
            the run we should run calculate_max_concurrent_usage_from_runs.
    Returns:
        Run: The created Run.

    """
    if no_instance_type:
        instance_type = None
    elif instance_type is None:
        instance_type = helper.get_random_instance_type()

    if not no_image and image is None:
        image = generate_aws_image()

    run = Run.objects.create(
        start_time=runtime[0],
        end_time=runtime[1],
        instance=instance,
        machineimage=image,
        instance_type=instance_type,
        vcpu=helper.SOME_EC2_INSTANCE_TYPES[instance_type]["vcpu"]
        if instance_type in helper.SOME_EC2_INSTANCE_TYPES
        else None,
        memory=helper.SOME_EC2_INSTANCE_TYPES[instance_type]["memory"]
        if instance_type in helper.SOME_EC2_INSTANCE_TYPES
        else None,
    )
    generate_single_aws_instance_event(
        instance=instance,
        occurred_at=runtime[0],
        event_type=InstanceEvent.TYPE.power_on,
        instance_type=instance_type,
        no_instance_type=no_instance_type,
    )
    if runtime[1]:
        generate_single_aws_instance_event(
            instance=instance,
            occurred_at=runtime[1],
            event_type=InstanceEvent.TYPE.power_off,
            instance_type=instance_type,
            no_instance_type=no_instance_type,
        )
    if calculate_concurrent_usage:
        calculate_max_concurrent_usage_from_runs([run])
    return run


def generate_aws_ec2_definitions():
    """Generate AwsEC2InstanceDefinitions from SOME_EC2_INSTANCE_TYPES."""
    instance_types = helper.SOME_EC2_INSTANCE_TYPES

    for name, instance in instance_types.items():
        __, created = AwsEC2InstanceDefinition.objects.get_or_create(
            instance_type=name,
            defaults={"memory": instance["memory"], "vcpu": instance["vcpu"]},
        )
        if not created:
            logger.warning('"%s" EC2 definition already exists', name)


def generate_cloudtrail_record(
    aws_account_id,
    event_name,
    event_time=None,
    region=None,
    request_parameters=None,
    response_elements=None,
):
    """
    Generate an example CloudTrail log's "Record" dict.

    This function needs something in request_parameters or response_elements to
    produce actually meaningful output, but this is not strictly required.

    Args:
        aws_account_id (int): The AWS account ID.
        event_name (str): optional AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.
        request_parameters (dict): optional data for 'requestParameters' key.
        response_elements (dict): optional data for 'responseElements' key.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    if not region:
        region = helper.get_random_region()
    if not event_time:
        event_time = helper.utc_dt(2018, 1, 1, 0, 0, 0)
    if not request_parameters:
        request_parameters = {}
    if not response_elements:
        response_elements = {}

    record = {
        "awsRegion": region,
        "eventName": event_name,
        "eventSource": "ec2.amazonaws.com",
        "eventTime": event_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "requestParameters": request_parameters,
        "responseElements": response_elements,
        "userIdentity": {"accountId": int(aws_account_id)},
    }
    return record


def generate_mock_cloudtrail_sqs_message(
    bucket_name="analyzer-test-bucket",
    object_key="path/to/file.json.gz",
    receipt_handle=None,
    message_id=None,
):
    """
    Generate a Mock object that behaves like a CloudTrail SQS message.

    Args:
        bucket_name (str): optional name of the S3 bucket
        object_key (str): optional path to the S3 object
        receipt_handle (str): optional SQS message receipt handle
        message_id (str): id of the message

    Returns:
        Mock: populated to look and behave like a CloudTrail SQS message

    """
    if not receipt_handle:
        receipt_handle = str(uuid.uuid4())

    if not message_id:
        message_id = str(uuid.uuid4())

    mock_sqs_message_body = {
        "Records": [
            {"s3": {"bucket": {"name": bucket_name,}, "object": {"key": object_key,},},}
        ]
    }
    mock_message = helper.generate_mock_sqs_message(
        message_id, json.dumps(mock_sqs_message_body), receipt_handle
    )
    return mock_message


def generate_cloudtrail_instances_record(
    aws_account_id,
    instance_ids,
    event_name="RunInstances",
    event_time=None,
    region=None,
    instance_type="t1.snail",
    image_id=None,
    subnet_id="subnet-12345678",
):
    """
    Generate an example CloudTrail log's "Record" dict for instances event.

    Args:
        aws_account_id (int): The AWS account ID.
        instance_ids (list[str]): The EC2 instance IDs relevant to the event.
        event_name (str): optional AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.
        instance_type (str): optional AWS instance type. Only used by
            RunInstances and the same value is effective for all instances.
        image_id (str): optional AWS AMI ID. Only used by RunInstances and the
            same value is effective for all instances.
        subnet_id (str): optional AWS EC2 subnet ID.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    if event_name == "RunInstances":
        request_parameters = {"instanceType": instance_type, "imageId": image_id}

        response_elements = {
            "instancesSet": {
                "items": [
                    {
                        "instanceId": instance_id,
                        "instanceType": instance_type,
                        "imageId": image_id,
                        "subnetId": subnet_id,
                    }
                    for instance_id in instance_ids
                ]
            },
        }
    else:
        request_parameters = {}
        response_elements = {
            "instancesSet": {
                "items": [{"instanceId": instance_id} for instance_id in instance_ids]
            },
        }

    record = generate_cloudtrail_record(
        aws_account_id,
        event_name,
        event_time,
        region,
        request_parameters=request_parameters,
        response_elements=response_elements,
    )
    return record


def generate_cloudtrail_tag_set_record(
    aws_account_id,
    image_ids,
    tag_names,
    event_name="CreateTags",
    event_time=None,
    region=None,
):
    """
    Generate an example CloudTrail log's "Record" dict for tag setting events.

    Args:
        aws_account_id (int): The AWS account ID.
        image_ids (list[str]): The EC2 AMI IDs whose tags are changing.
        tag_names (list[str]): List of tags
        event_name (str): AWS event name.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    request_parameters = {
        "resourcesSet": {"items": [{"resourceId": image_id} for image_id in image_ids]},
        "tagSet": {
            "items": [{"key": tag_name, "value": tag_name} for tag_name in tag_names]
        },
    }
    record = generate_cloudtrail_record(
        aws_account_id,
        event_name,
        event_time,
        region,
        request_parameters=request_parameters,
    )
    return record


def generate_cloudtrail_modify_instance_record(
    aws_account_id, instance_id, instance_type="t2.micro", event_time=None, region=None,
):
    """
    Generate an example CloudTrail "ModifyInstanceAttribute" record dict.

    Args:
        aws_account_id (int): The AWS account ID.
        instance_id (str): The EC2 instance ID relevant to the event.
        instance_type (str): New instance type.
        event_time (datetime.datetime): optional time when the even occurred.
        region (str): optional AWS region in which the event occurred.

    Returns:
        dict: Data that looks like a CloudTrail log Record.

    """
    event_name = "ModifyInstanceAttribute"
    request_parameters = {
        "instanceId": instance_id,
        "instanceType": {"value": instance_type},
    }
    record = generate_cloudtrail_record(
        aws_account_id,
        event_name,
        event_time,
        region,
        request_parameters=request_parameters,
    )
    return record


def recalculate_runs_from_events(events):
    """
    Run recalculate_runs on multiple events.

    Args:
        events (list(model.InstanceEvents)): events to recalculate

    """
    for event in events:
        recalculate_runs(event)


def create_messages_for_sqs(count=1):
    """
    Create lists of messages for testing SQS interactions.

    Args:
        count (int): number of messages to generate

    Returns:
        tuple: Three lists. The first list contains the original message
            payloads. The second list contains the messages wrapped as we
            would batch send to SQS. The third list contains the messages
            wrapped as we would received from SQS.

    """
    payloads = []
    messages_sent = []
    messages_received = []
    for __ in range(count):
        message = f"Hello, {uuid.uuid4()}!"
        wrapped = _sqs_wrap_message(message)
        payloads.append(message)
        messages_sent.append(wrapped)
        received = {
            "Id": wrapped["Id"],
            "Body": wrapped["MessageBody"],
            "ReceiptHandle": uuid.uuid4(),
        }
        messages_received.append(received)
    return payloads, messages_sent, messages_received
