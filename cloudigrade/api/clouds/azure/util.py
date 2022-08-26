"""Utility functions for Azure models and use cases."""
import logging

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.azure.models import (
    AzureCloudAccount,
    AzureMachineImage,
)
from api.models import (
    CloudAccount,
    InstanceEvent,
    MachineImage,
)


logger = logging.getLogger(__name__)


def create_azure_cloud_account(
    user,
    subscription_id,
    platform_authentication_id,
    platform_application_id,
    platform_source_id,
):
    """
    Create AzureCloudAccount for the customer user.

    This function may raise ValidationError if certain verification steps fail.

    We call CloudAccount.enable after creating it, and that effectively verifies Azure
    permission. If that fails, we must abort this creation.
    That is why we put almost everything here in a transaction.atomic() context.

    Args:
        user (api.User): user to own the CloudAccount
        subscription_id (str): UUID of the customer subscription
        platform_authentication_id (str): Platform Sources' Authentication object id
        platform_application_id (str): Platform Sources' Application object id
        platform_source_id (str): Platform Sources' Source object id

    Returns:
        CloudAccount the created cloud account.

    """
    logger.info(
        _(
            "Creating an AzureCloudAccount. "
            "account_number=%(account_number)s, "
            "org_id=%(org_id)s, "
            "subscription_id=%(subscription_id)s, "
            "platform_authentication_id=%(platform_authentication_id)s, "
            "platform_application_id=%(platform_application_id)s, "
            "platform_source_id=%(platform_source_id)s"
        ),
        {
            "account_number": user.account_number,
            "org_id": user.org_id,
            "subscription_id": subscription_id,
            "platform_authentication_id": platform_authentication_id,
            "platform_application_id": platform_application_id,
            "platform_source_id": platform_source_id,
        },
    )

    with transaction.atomic():
        try:
            azure_cloud_account = AzureCloudAccount.objects.create(
                subscription_id=subscription_id
            )
        except IntegrityError:
            # create can raise IntegrityError if the given
            # subscription_id already exists in an account
            error_code = error_codes.CG1005
            error_code.notify(user.account_number, user.org_id, platform_application_id)
            raise ValidationError({"subscription_id": error_code.get_message()})

        cloud_account = CloudAccount.objects.create(
            user=user,
            content_object=azure_cloud_account,
            platform_application_id=platform_application_id,
            platform_authentication_id=platform_authentication_id,
            platform_source_id=platform_source_id,
        )

        # This enable call *must* be inside the transaction because we need to
        # know to rollback the transaction if anything related to enabling fails.
        if not cloud_account.enable(disable_upon_failure=False):
            # Enabling of cloud account failed, rolling back.
            transaction.set_rollback(True)
            raise ValidationError(
                {
                    "is_enabled": "Could not enable cloud account. "
                    "Please check your credentials."
                }
            )

    return cloud_account


def create_new_machine_images(vms_data):
    """
    Create AzureMachineImage objects that have not been seen before.

    Model AzureMachineImage:
    resource_id (varchar)                  vm.storage_profile.image_reference.sku
    azure_marketplace_image (boolean)
    region (varchar)

    Returns:
        list: A list of image ids that were added to the database
    """
    log_prefix = "create_new_machine_image"

    known_skus = {
        azure_machine_image.resource_id
        for azure_machine_image in AzureMachineImage.objects.all()
    }

    new_skus = []
    for vm in vms_data:
        sku = vm["image"]["sku"]
        if sku not in list(known_skus):
            logger.info(
                _("%(prefix)s: Saving new Azure Machine Image sku: %(sku)s"),
                {"prefix": log_prefix, "sku": sku},
            )
            name = sku
            rhel_detected_by_tag = False
            status = MachineImage.PENDING
            openshift_detected = False
            image, new = save_new_azure_machine_image(
                resource_id=sku,
                azure_marketplace_image=vm["azure_marketplace_image"],
                region=vm["region"],
                inspection_json=vm["inspection_json"],
                name=name,
                is_encrypted=vm["is_encrypted"],
                status=status,
                openshift_detected=openshift_detected,
                rhel_detected_by_tag=rhel_detected_by_tag,
                architecture=vm["architecture"],
            )
            if new:
                new_skus.append(sku)

    return new_skus


def save_new_azure_machine_image(
    resource_id,
    azure_marketplace_image,
    region,
    inspection_json,
    name,
    is_encrypted,
    status,
    openshift_detected,
    rhel_detected_by_tag,
    architecture,
):
    """
    Save a new AzureMachineImage image object.

    Args:
        resource_id (str): The Azure image identifier
        azure_marketplace_image (boolean): True if the image is from the marketplace
        region (str): Region where the image was found
    """
    with transaction.atomic():
        azuremachineimage, created = AzureMachineImage.objects.get_or_create(
            resource_id=resource_id,
            azure_marketplace_image=azure_marketplace_image,
            region=region,
        )

        if created:
            logger.info(
                _("save_new_azure_machine_image created %(azuremachineimage)s"),
                {"azuremachineimage": azuremachineimage},
            )
            machineimage = MachineImage.objects.create(
                architecture=architecture,
                content_object=azuremachineimage,
                name=name,
                inspection_json=inspection_json,
                is_encrypted=is_encrypted,
                openshift_detected=openshift_detected,
                rhel_detected_by_tag=rhel_detected_by_tag,
                status=status,
            )
            logger.info(
                _("save_new_azure_machine_image created %(machineimage)s"),
                {"machineimage": machineimage},
            )
        azuremachineimage.machine_image.get()

    return azuremachineimage, created


def create_initial_azure_instance_events(account, vms_data):
    """
    Create AzureInstance and AzureInstanceEvent the first time we see a vm.

    Model AzureInstance:
    resource_id (varchar)               vm.id
    region (varchar)

    Model AzureInstanceEvent:
    instance_type (varchar)

    Args:
        account (CloudAccount): The account that owns the vm that spawned
            the data for these InstanceEvents.
        vms_data (dict): Dict of discovereds vms for the account subscription.
    """


@transaction.atomic()
def save_instance(account, vm_data, region):
    """
    Create or Update the instance object for the Azure vm.

    Args:
        account (CloudAccount): The account that owns the vm that spawned
            the data for this Instance.
        vm_data (dict): Dict of the details of this vm
        region (str): Azure region

    Returns:
        AzureInstance: Object representing the saved instance.
    """


def save_instance_events(azureinstance, vm_data, events=None):
    """
    Save provided events, and create the instance object if it does not exist.

    Args:
        azureinstance (AzureInstance): The Instnace associated with these
            InstanceEvents.
        vm_data (dict): Dictionary containing instance information.
        region (str): Azure region
        events(list[dict]): List of dicts representing Evnts to be saved.

    Retunrs:
        AzureInstance: Object representing the saved instnace.
    """


def get_instance_event_type(vm):
    """Return the InstanceEvent type for the vm specified."""
    if vm and vm["running"]:
        return InstanceEvent.TYPE.power_on
    else:
        return InstanceEvent.TYPE.power_off
