"""Helper functions for generating test data."""
import functools
import json
import logging
import random
import uuid
from datetime import timedelta
from unittest.mock import patch

import faker
from django.conf import settings
from django.db.models import ForeignKey
from rest_framework.test import APIClient

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from api.clouds.aws import tasks
from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    CLOUD_ACCESS_NAME_TOKEN,
    MARKETPLACE_NAME_TOKEN,
)
from api.clouds.azure.models import (
    AzureCloudAccount,
    AzureInstance,
    AzureInstanceEvent,
    AzureMachineImage,
)
from api.models import (
    CloudAccount,
    Instance,
    InstanceDefinition,
    InstanceEvent,
    MachineImage,
    Run,
)
from api.util import (
    calculate_max_concurrent_usage,
    calculate_max_concurrent_usage_from_runs,
    recalculate_runs,
)
from util import aws
from util.misc import get_now
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

    def __init__(self, api_root="/api/cloudigrade/v2"):
        """Initialize the client."""
        self.client = APIClient()
        self.authenticated_user = None
        self.aws_account_verified = True
        self.aws_primary_account_id = int(helper.generate_dummy_aws_account_id())
        self.api_root = api_root

    def _call_api(self, verb, path, data=None, *args, **kwargs):
        """
        Make the simulated API call, optionally patching cloud interactions.

        The following objects are *always* patched to remove potential external calls
        so we remain more truly "sandboxed" for the duration of this request:

        - aws.verify_account_access is used in account creation
        - aws.sts.boto3 is used in account creation
        - api.serializers.verify_permissions is used in account creation
        - aws.delete_cloudtrail is used in account deletion
        - aws.get_session is used in account deletion
        - aws.sts._get_primary_account_id is used in sysconfig
        - tasks.initial_aws_describe_instances is used in account creation

        Returns:
            rest_framework.response.Response
        """
        with patch.object(aws, "verify_account_access") as mock_verify, patch(
            "api.clouds.aws.util.verify_permissions"
        ) as mock_verify_permissions, patch.object(aws.sts, "boto3"), patch.object(
            aws, "delete_cloudtrail"
        ), patch.object(
            aws, "get_session"
        ), patch.object(
            aws.sts, "_get_primary_account_id"
        ) as mock_get_primary_account_id, patch.object(
            tasks, "initial_aws_describe_instances"
        ):
            mock_verify.return_value = self.aws_account_verified, []
            mock_verify_permissions.return_value = True
            mock_get_primary_account_id.return_value = self.aws_primary_account_id
            response = getattr(self.client, verb)(path, data=data, *args, **kwargs)
        return response

    def __getattr__(self, item):
        """
        Get an appropriate RESTful API-calling method.

        If we want to customize any specific API's behavior, we can simply add
        a new method to this class following the "verb_noun" pattern. For
        example, "create_account" would handle POSTs to the account API.
        """
        try:
            verb, noun = item.split("_", 1)
            if verb == "list":
                verb = "get"
            elif verb == "create":
                verb = "post"
            return functools.partial(self.verb_noun, verb, noun)
        except Exception:
            raise AttributeError(
                f"'{self.__class__.__name__}' object " f"has no attribute '{item}'"
            )

    def _force_authenticate(self, user, credential_headers=None):
        """Force client authentication as the given user."""
        self.authenticated_user = user
        if credential_headers:
            self.client.credentials(**credential_headers)

    def verb_noun(
        self,
        verb,
        noun,
        noun_id=None,
        detail=None,
        data=None,
        api_root=None,
        *args,
        **kwargs,
    ):
        """Make a simulated REST API call for the given inputs."""
        if api_root is None:
            api_root = self.api_root
        if detail:
            path = f"{api_root}/{noun}/{noun_id}/{detail}/"
        elif noun_id:
            path = f"{api_root}/{noun}/{noun_id}/"
        elif verb == "report":
            path = f"{api_root}/report/{noun}/"
            verb = "get"
        else:
            path = f"{api_root}/{noun}/"
        return self._call_api(verb=verb, path=path, data=data, *args, **kwargs)


def generate_cloud_account(cloud_type=AWS_PROVIDER_STRING, **kwargs):
    """
    Generate a CloudAccount with linked provider-specific model instance for testing.

    Note:
        This function may be deprecated and removed in the near future since we will
        stop assuming AWS is a default as we improve support for additional cloud types.
        Please use a cloud-specific function (e.g. generate_cloud_account_aws,
        generate_cloud_account_azure) instead of this.

    Args:
        cloud_type (str): cloud provider type identifier
        **kwargs (dict): Optional additional kwargs to pass to generate_cloud_account.

    Returns:
        CloudAccount: The created CloudAccount instance.
    """
    if cloud_type == AWS_PROVIDER_STRING:
        return generate_cloud_account_aws(**kwargs)
    elif cloud_type == AZURE_PROVIDER_STRING:
        return generate_cloud_account_azure(**kwargs)
    else:
        raise NotImplementedError(f"Unsupported cloud_type '{cloud_type}'")


def generate_cloud_account_aws(
    arn=None,
    aws_account_id=None,
    created_at=None,
    **kwargs,
):
    """
    Generate a CloudAccount with linked AwsCloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        arn (str): Optional ARN.
        aws_account_id (str): Optional 12-digit AWS account ID.
        created_at (datetime): Optional creation datetime for this account.
        **kwargs (dict): Optional additional kwargs to pass to generate_cloud_account.

    Returns:
        CloudAccount: The created CloudAccount instance.
    """
    if arn is None:
        arn = helper.generate_dummy_arn(account_id=aws_account_id)

    if created_at is None:
        created_at = get_now()

    provider_cloud_account = AwsCloudAccount.objects.create(
        account_arn=arn,
        aws_account_id=aws.AwsArn(arn).account_id,
    )
    provider_cloud_account.created_at = created_at
    provider_cloud_account.save()

    return _generate_cloud_account(
        provider_cloud_account, created_at=created_at, **kwargs
    )


def generate_cloud_account_azure(
    azure_subscription_id=None,
    created_at=None,
    **kwargs,
):
    """
    Generate a CloudAccount with linked AzureCloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        azure_subscription_id (str): optional uuid str for azure subscription id
        created_at (datetime): Optional creation datetime for this account.
        **kwargs (dict): Optional additional kwargs to pass to generate_cloud_account.

    Returns:
        CloudAccount: The created CloudAccount instance.
    """
    if created_at is None:
        created_at = get_now()

    if azure_subscription_id is None:
        azure_subscription_id = uuid.uuid4()

    provider_cloud_account = AzureCloudAccount.objects.create(
        subscription_id=azure_subscription_id,
    )
    provider_cloud_account.created_at = created_at
    provider_cloud_account.save()

    return _generate_cloud_account(
        provider_cloud_account, created_at=created_at, **kwargs
    )


def _generate_cloud_account(
    provider_cloud_account,
    user=None,
    created_at=None,
    platform_authentication_id=None,
    platform_application_id=None,
    platform_application_is_paused=False,
    platform_source_id=None,
    is_enabled=True,
    enabled_at=None,
    missing_content_object=False,
    is_synthetic=False,
):
    """
    Generate a CloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        provider_cloud_account (object): the provider-specific cloud account
            model instance (e.g. AwsCloudAccount, AzureCloudAccount) to be linked with
            the newly-created CloudAccount
        user (User): Optional Django auth User to be this account's owner.
        created_at (datetime): Optional creation datetime for this account.
        platform_authentication_id (int): Optional platform source authentication ID.
        platform_application_id (int): Optional platform source application ID.
        platform_source_id (int): Optional platform source source ID.
        is_enabled (bool): Optional should the account be enabled.
        enabled_at (datetime): Optional enabled datetime for this account.
        missing_content_object (bool): should the provider-specific cloud account
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the CloudAccount.
        is_synthetic (bool): Optional should the account be treated as if it originated
            from a SyntheticDataRequest.

    Returns:
        CloudAccount: The created Cloud Account.

    """
    if user is None:
        user = helper.generate_test_user()

    if created_at is None:
        created_at = get_now()

    if enabled_at is None:
        enabled_at = created_at

    if platform_authentication_id is None:
        platform_authentication_id = _faker.pyint()

    if platform_application_id is None:
        platform_application_id = _faker.pyint()

    if platform_source_id is None:
        platform_source_id = _faker.pyint()

    cloud_account = CloudAccount.objects.create(
        user=user,
        content_object=provider_cloud_account,
        platform_authentication_id=platform_authentication_id,
        platform_application_id=platform_application_id,
        platform_application_is_paused=platform_application_is_paused,
        platform_source_id=platform_source_id,
        is_enabled=is_enabled,
        enabled_at=enabled_at,
        is_synthetic=is_synthetic,
    )
    cloud_account.created_at = created_at
    cloud_account.save()

    if missing_content_object:
        provider_cloud_account_class = cloud_account.content_object.__class__
        content_object_queryset = provider_cloud_account_class.objects.filter(
            id=cloud_account.content_object.id
        )
        # Use _raw_delete so we don't trigger any signals or other model side-effects.
        content_object_queryset._raw_delete(content_object_queryset.db)
        # We need to get a fresh instance, not just use .refresh_from_db() because the
        # generic relation doesn't seem to update when calling .refresh_from_db() here.
        cloud_account = CloudAccount.objects.get(id=cloud_account.id)

    return cloud_account


def generate_instance(cloud_account, **kwargs):
    """
    Generate an Instance with linked provider-specific model instance for testing.

    Note:
        Please consider using a cloud-specific function (e.g. generate_instance_aws,
        generate_instance_azure) instead of this.

    Args:
        cloud_account (CloudAccount): account that owns the instance.
        **kwargs (dict): Optional additional kwargs to pass to type-specific function.

    Returns:
        Instance: The created Instance instance.
    """
    if isinstance(cloud_account.content_object, AwsCloudAccount):
        return generate_instance_aws(cloud_account, **kwargs)
    elif isinstance(cloud_account.content_object, AzureCloudAccount):
        return generate_instance_azure(cloud_account, **kwargs)
    else:
        raise NotImplementedError(
            f"Unsupported cloud account type '{cloud_account.content_object.__class__}'"
        )


def generate_instance_azure(
    cloud_account,
    region=None,
    image=None,
    no_image=False,
    azure_instance_resource_id=None,
    missing_content_object=False,
):
    """
    Generate an AzureInstance for the given CloudAccount for testing.

    Any optional arguments not provided will be randomly generated.

    Args:
        cloud_account (CloudAccount): Account that will own the instance.
        region (str): Optional Azure region where the instance runs.
        image (MachineImage): Optional image to add instead of creating one.
        no_image (bool): Whether an image should be attached to this instance.
        azure_instance_resource_id (str): optional str for azure instance resource id
        missing_content_object (bool): should the provider-specific cloud account
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the Instance.

    Returns:
        Instance: The created Instance.

    """
    cloud_type = AZURE_PROVIDER_STRING
    if region is None:
        region = helper.get_random_region(cloud_type=cloud_type)
    if azure_instance_resource_id is None:
        azure_instance_resource_id = helper.generate_dummy_azure_instance_id()
    if image is None and not no_image:
        image_resource_id = helper.generate_dummy_azure_image_id()
        try:
            azure_image = AzureMachineImage.objects.get(resource_id=image_resource_id)
            image = azure_image.machine_image.get()
        except AzureMachineImage.DoesNotExist:
            image = generate_image(
                azure_image_resource_id=image_resource_id,
                status=MachineImage.PENDING,
                cloud_type=cloud_type,
            )
    azure_instance = AzureInstance.objects.create(
        resource_id=azure_instance_resource_id,
        region=region,
    )
    instance = Instance.objects.create(
        cloud_account=cloud_account,
        content_object=azure_instance,
        machine_image=image,
    )

    if missing_content_object:
        content_object_queryset = AzureInstance.objects.filter(id=azure_instance.id)
        # Use _raw_delete so we don't trigger any signals or other model side-effects.
        content_object_queryset._raw_delete(content_object_queryset.db)
        # We need to get a fresh instance, not just use .refresh_from_db() because the
        # generic relation doesn't seem to update when calling .refresh_from_db() here.
        instance = Instance.objects.get(id=instance.id)

    return instance


def generate_instance_aws(
    cloud_account,
    ec2_instance_id=None,
    region=None,
    image=None,
    no_image=False,
    missing_content_object=False,
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
        missing_content_object (bool): should the provider-specific cloud account
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the Instance.

    Returns:
        Instance: The created Instance.

    """
    cloud_type = AWS_PROVIDER_STRING

    if region is None:
        region = helper.get_random_region(cloud_type=cloud_type)

    if ec2_instance_id is None:
        ec2_instance_id = helper.generate_dummy_instance_id()
    if image is None and not no_image:
        ec2_ami_id = helper.generate_dummy_image_id()
        try:
            aws_image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
            image = aws_image.machine_image.get()
        except AwsMachineImage.DoesNotExist:
            aws_account_id = cloud_account.content_object.aws_account_id
            image = generate_image(
                ec2_ami_id=ec2_ami_id,
                owner_aws_account_id=aws_account_id,
                status=MachineImage.PENDING,
            )

    aws_instance = AwsInstance.objects.create(
        ec2_instance_id=ec2_instance_id,
        region=region,
    )
    instance = Instance.objects.create(
        cloud_account=cloud_account,
        content_object=aws_instance,
        machine_image=image,
    )

    if missing_content_object:
        content_object_queryset = AwsInstance.objects.filter(id=aws_instance.id)
        # Use _raw_delete so we don't trigger any signals or other model side-effects.
        content_object_queryset._raw_delete(content_object_queryset.db)
        # We need to get a fresh instance, not just use .refresh_from_db() because the
        # generic relation doesn't seem to update when calling .refresh_from_db() here.
        instance = Instance.objects.get(id=instance.id)

    return instance


def generate_single_instance_event(
    instance,
    occurred_at,
    event_type=None,
    instance_type=None,
    subnet=None,
    no_instance_type=False,
    no_subnet=False,
    cloud_type=AWS_PROVIDER_STRING,
    missing_content_object=False,
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
        cloud_type (str): cloud provider type identifier
        missing_content_object (bool): should the provider-specific instance event
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the InstanceEvent.

    Returns:
        AwsInstanceEvent: The created AwsInstanceEvent.

    """
    if no_instance_type:
        instance_type = None
    elif instance_type is None:
        instance_type = helper.get_random_instance_type(cloud_type=cloud_type)

    if event_type is None:
        event_type = InstanceEvent.TYPE.power_off

    if cloud_type == AZURE_PROVIDER_STRING:
        cloud_provider_event = AzureInstanceEvent.objects.create(
            instance_type=instance_type,
        )

    else:
        if no_subnet:
            subnet = None
        elif subnet is None:
            subnet = helper.generate_dummy_subnet_id()

        cloud_provider_event = AwsInstanceEvent.objects.create(
            subnet=subnet,
            instance_type=instance_type,
        )
    event = InstanceEvent.objects.create(
        instance=instance,
        event_type=event_type,
        occurred_at=occurred_at,
        content_object=cloud_provider_event,
    )

    if missing_content_object:
        provider_instance_event_class = cloud_provider_event.__class__
        content_object_queryset = provider_instance_event_class.objects.filter(
            id=cloud_provider_event.id
        )
        # Use _raw_delete so we don't trigger any signals or other model side-effects.
        content_object_queryset._raw_delete(content_object_queryset.db)
        # We need to get a fresh instance, not just use .refresh_from_db() because the
        # generic relation doesn't seem to update when calling .refresh_from_db().
        event = InstanceEvent.objects.get(id=event.id)

    return event


def generate_instance_events(
    instance,
    powered_times,
    instance_type=None,
    subnet=None,
    no_instance_type=False,
    cloud_type=AWS_PROVIDER_STRING,
    missing_content_object=False,
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
        cloud_type (str): cloud provider type identifier
        missing_content_object (bool): should the provider-specific instance event
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the InstanceEvent.

    Returns:
        list(InstanceEvent): The list of created AwsInstanceEvents.

    """
    if no_instance_type:
        instance_type = None
    elif instance_type is None:
        instance_type = helper.get_random_instance_type(cloud_type=cloud_type)
    if subnet is None:
        subnet = helper.generate_dummy_subnet_id()

    events = []
    for power_on_time, power_off_time in powered_times:
        if power_on_time is not None:
            event = generate_single_instance_event(
                instance=instance,
                occurred_at=power_on_time,
                event_type=InstanceEvent.TYPE.power_on,
                instance_type=instance_type,
                subnet=subnet,
                no_instance_type=no_instance_type,
                cloud_type=cloud_type,
                missing_content_object=missing_content_object,
            )
            events.append(event)
        if power_off_time is not None:
            # power_off events typically do *not* have an image defined.
            # So, ignore inputs and *always* set ec2_ami_id=None.
            event = generate_single_instance_event(
                instance=instance,
                occurred_at=power_off_time,
                event_type=InstanceEvent.TYPE.power_off,
                instance_type=instance_type,
                subnet=subnet,
                no_instance_type=no_instance_type,
                cloud_type=cloud_type,
                missing_content_object=missing_content_object,
            )
            events.append(event)
    return events


def generate_image(cloud_type=AWS_PROVIDER_STRING, **kwargs):
    """
    Generate a MachineImage with linked provider-specific model instance for testing.

    Note:
        This function may be deprecated and removed in the near future since we will
        stop assuming AWS is a default as we improve support for additional cloud types.
        Please use a cloud-specific function (e.g. generate_image_aws,
        generate_image_azure) instead of this.

    Args:
        cloud_type (str): cloud provider type identifier
        **kwargs (dict): Optional additional kwargs to pass to type-specific function.

    Returns:
        MachineImage: The created MachineImage instance.
    """
    if cloud_type == AWS_PROVIDER_STRING:
        return generate_image_aws(**kwargs)
    elif cloud_type == AZURE_PROVIDER_STRING:
        return generate_image_azure(**kwargs)
    else:
        raise NotImplementedError(f"Unsupported cloud_type '{cloud_type}'")


def _generate_image(
    provider_machine_image,
    name=None,
    status=MachineImage.INSPECTED,
    is_encrypted=False,
    rhel_detected=False,
    rhel_detected_by_tag=False,
    rhel_detected_repos=False,
    rhel_detected_certs=False,
    rhel_detected_release_files=False,
    rhel_detected_signed_packages=False,
    rhel_version=None,
    syspurpose=None,
    openshift_detected=False,
    architecture="x86_64",
    missing_content_object=False,
):
    """
    Generate a MachineImage linked to the given provider-specific model instance.

    Args:
        provider_machine_image (object): cloud provider specific MachineImage instance
        name (str): image name
        status (str): MachineImage inspection status
        is_encrypted (bool): is image filesystem data encrypted
        rhel_detected (bool): is RHEL detected by any unspecified method
        rhel_detected_by_tag (bool): is RHEL detected by tag
        rhel_detected_repos (bool): is RHEL detected via enabled yum/dnf repos
        rhel_detected_certs (bool): is RHEL detected via product certificates
        rhel_detected_release_files (bool): is RHEL detected via release files
        rhel_detected_signed_packages (bool): is RHEL detected via signed packages
        rhel_version (str): RHEL version string
        syspurpose (dict): syspurpose JSON file contents
        openshift_detected (bool): is OpenShift detected
        architecture (str): image's CPU architecture
        missing_content_object (bool): should the provider-specific machine image
            (content_object) be missing; this is used to simulate unwanted edge cases in
            which the content_object is not correctly deleted with the MachineImage.

    Returns:
        MachineImage: The created MachineImage instance.
    """
    if rhel_detected:
        if not syspurpose:
            syspurpose = generate_syspurpose()
        if not any(
            (
                rhel_detected_certs,
                rhel_detected_release_files,
                rhel_detected_repos,
                rhel_detected_signed_packages,
            )
        ):
            inspection_json = json.dumps(
                {
                    "rhel_release_files_found": rhel_detected,
                    "syspurpose": syspurpose,
                }
            )
        else:
            inspection_json = json.dumps(
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
        inspection_json = None

    machine_image = MachineImage.objects.create(
        is_encrypted=is_encrypted,
        inspection_json=inspection_json,
        rhel_detected_by_tag=rhel_detected_by_tag,
        openshift_detected=openshift_detected,
        name=name,
        status=status,
        content_object=provider_machine_image,
        architecture=architecture,
    )

    if missing_content_object:
        provider_machine_image_class = machine_image.content_object.__class__
        content_object_queryset = provider_machine_image_class.objects.filter(
            id=machine_image.content_object.id
        )
        # Use _raw_delete so we don't trigger any signals or other model side-effects.
        content_object_queryset._raw_delete(content_object_queryset.db)
        # We need to get a fresh instance, not just use .refresh_from_db() because the
        # generic relation doesn't seem to update when calling .refresh_from_db() here.
        machine_image = MachineImage.objects.get(id=machine_image.id)

    return machine_image


def generate_image_aws(
    owner_aws_account_id=None,
    name=None,
    ec2_ami_id=None,
    is_marketplace=False,
    is_cloud_access=False,
    is_windows=False,
    product_codes=None,
    platform_details=None,
    usage_operation=None,
    generate_marketplace_product_code=False,
    **kwargs,
):
    """
    Generate a MachineImage with linked AwsMachineImage for testing.

    Values will be randomly generated for any missing optional arguments.

    Args:
        name (str): AMI name
        owner_aws_account_id (int): AWS account ID that owns the image
        ec2_ami_id (str): EC2 AMI ID of the image
        is_marketplace (bool): is the image from the AWS Marketplace. If true, this also
            overrides the owner_aws_account_id and name as appropriate.
        is_cloud_access (bool): is the image from Cloud Access. If true, this also
            overrides the owner_aws_account_id and name as appropriate.
        is_windows (bool): is the AMI Windows
        product_codes (list[dict]): AMI product codes
        platform_details (str): AMI platform details (e.g. "Linux/UNIX")
        usage_operation (str): AMI usage operation (e.g. "RunInstances:0010")
        generate_marketplace_product_code (bool): generate a marketplace product code
        **kwargs (dict): additional optional arguments for _generate_image

    Returns:
        MachineImage: The created MachineImage instance.

    """
    if not owner_aws_account_id:
        owner_aws_account_id = helper.generate_dummy_aws_account_id()
    if not ec2_ami_id:
        ec2_ami_id = helper.generate_dummy_image_id()
    platform = AwsMachineImage.WINDOWS if is_windows else AwsMachineImage.NONE

    aws_marketplace_image = False
    if is_marketplace:
        name = f"{name or _faker.name()}{MARKETPLACE_NAME_TOKEN}"
        owner_aws_account_id = random.choice(settings.RHEL_IMAGES_AWS_ACCOUNTS)
        # Note: At the time of this writing, we do not set aws_marketplace_image=True
        # during image describe operations based on the name and owner account.
        # We only check at AwsMachineImage.is_marketplace runtime to see if the name
        # and owner contain values that would indicate marketplace as its origin.

    if is_cloud_access:
        name = f"{name or _faker.name()}{CLOUD_ACCESS_NAME_TOKEN}"
        owner_aws_account_id = random.choice(settings.RHEL_IMAGES_AWS_ACCOUNTS)

    if generate_marketplace_product_code:
        if not product_codes:
            product_codes = []
        product_codes.append({"ProductCodeType": aws.AWS_PRODUCT_CODE_TYPE_MARKETPLACE})
        aws_marketplace_image = True

    aws_machine_image = AwsMachineImage.objects.create(
        owner_aws_account_id=owner_aws_account_id,
        ec2_ami_id=ec2_ami_id,
        platform=platform,
        product_codes=product_codes,
        platform_details=platform_details,
        usage_operation=usage_operation,
        aws_marketplace_image=aws_marketplace_image,
    )

    machine_image = _generate_image(aws_machine_image, name, **kwargs)

    return machine_image


def generate_image_azure(azure_image_resource_id=None, is_marketplace=False, **kwargs):
    """
    Generate a MachineImage with linked AwsMachineImage for testing.

    Values will be randomly generated for any missing optional arguments.

    Args:
        azure_image_resource_id (str): Azure image resource ID (UUID)
        is_marketplace (bool): is the image from the Azure Marketplace.
        **kwargs (dict): additional optional arguments for _generate_image

    Returns:
        MachineImage: The created MachineImage instance.

    """
    if azure_image_resource_id is None:
        azure_image_resource_id = helper.generate_dummy_azure_image_id()

    azure_machine_image = AzureMachineImage.objects.create(
        resource_id=azure_image_resource_id,
        azure_marketplace_image=is_marketplace,
    )

    machine_image = _generate_image(azure_machine_image, **kwargs)

    return machine_image


def generate_syspurpose(role=None, sla=None, usage=None, service_type=None):
    """
    Generate a syspurpose for testing.

    Args:
        role (str): Optional. Role to specify.
        sla (str): Optional. SLA to specify.
        usage (str): Optional. Usage to specify.

    Returns:
        dict: A dictionary representing a syspurpose.

    """
    roles = [
        "Red Hat Enterprise Linux Server",
        "Red Hat Enterprise Linux Workstation",
        "Red Hat Enterprise Linux Compute Node",
    ]
    slas = [
        "Premium",
        "Standard",
        "Self-Support",
    ]
    usages = [
        "Production",
        "Disaster Recovery",
        "Development/Test",
    ]

    service_types = ["PSF", "L3", "L1-L3", "Embedded L3"]
    if not role:
        role = random.choice(roles)
    if not sla:
        sla = random.choice(slas)
    if not usage:
        usage = random.choice(usages)
    if not service_type:
        service_type = random.choice(service_types)
    return {
        "role": role,
        "service_level_agreement": sla,
        "usage": usage,
        "service_type": service_type,
    }


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
        image = generate_image()

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
    generate_single_instance_event(
        instance=instance,
        occurred_at=runtime[0],
        event_type=InstanceEvent.TYPE.power_on,
        instance_type=instance_type,
        no_instance_type=no_instance_type,
    )
    if runtime[1]:
        generate_single_instance_event(
            instance=instance,
            occurred_at=runtime[1],
            event_type=InstanceEvent.TYPE.power_off,
            instance_type=instance_type,
            no_instance_type=no_instance_type,
        )
    if calculate_concurrent_usage:
        calculate_max_concurrent_usage_from_runs([run])
    return run


def generate_instance_type_definitions(cloud_type="aws"):
    """Generate InstanceDefinitions from SOME_EC2_INSTANCE_TYPES."""
    instance_types = helper.SOME_EC2_INSTANCE_TYPES

    for name, instance in instance_types.items():
        __, created = InstanceDefinition.objects.get_or_create(
            instance_type=name,
            cloud_type=cloud_type,
            defaults={
                "memory_mib": instance["memory"],
                "vcpu": instance["vcpu"],
                "json_definition": instance["json_definition"],
            },
        )
        if not created:
            logger.warning('"%s" EC2 definition already exists', name)


def recalculate_runs_from_events(events):
    """
    Run recalculate_runs on multiple events.

    Args:
        events (list(model.InstanceEvents)): events to recalculate

    """
    for event in events:
        recalculate_runs(event)


def calculate_concurrent(start_date, end_date, user_id):
    """Calculate the concurrent usage between two dates."""
    delta = end_date - start_date
    for i in range(delta.days + 1):
        day = start_date + timedelta(days=i)
        calculate_max_concurrent_usage(date=day, user_id=user_id)


class ModelStrTestMixin:
    """Mixin for test classes to add common assertion for str correctness."""

    def assertTypicalStrOutput(self, instance, exclude_field_names=None):
        """
        Assert instance's str output includes all relevant data.

        Our typical model string representation should look like:
            ClassName(field="value", other_field="value", related_model_id=1)
        """
        if exclude_field_names is None:
            exclude_field_names = ()
        output = str(instance)
        self.assertEqual(output, repr(instance))
        self.assertTrue(output.startswith(f"{instance.__class__.__name__}("))
        field_names = (
            field.name if not isinstance(field, ForeignKey) else f"{field.name}_id"
            for field in instance.__class__._meta.local_fields
            if field.name not in exclude_field_names
        )
        for field_name in field_names:
            self.assertIn(f"{field_name}=", output)
