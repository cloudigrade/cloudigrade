"""Utility methods to handle azure virtual machines."""
import json
import logging

from azure.core.exceptions import ClientAuthenticationError
from azure.mgmt.compute import ComputeManagementClient
from django.utils.translation import gettext as _

from util import azure

logger = logging.getLogger(__name__)

# References
# https://stackoverflow.com/questions/71656714/
#   how-to-check-os-detailed-information-of-azure-virtual-machine-using-python-sdk
# https://docs.microsoft.com/en-us/previous-versions/azure/virtual-machines/windows/python#get-information-about-the-vm


def get_vms_for_subscription(azure_subscription_id):
    """Discover vms for a particular subscription."""
    try:
        cm_client = ComputeManagementClient(
            azure.get_cloudigrade_credentials(),
            azure_subscription_id,
        )

        # with statusOnly to list_all to get the instanceView, we do not get the
        # hardware and storage profiles, so we need 2 queries to get the whole set.
        # still much better than n+1 to get the instanceView for each vm since
        # we only have a total of 2 queries.
        vm_list = cm_client.virtual_machines.list_all()
        vm_list_with_status = cm_client.virtual_machines.list_all(
            params={"statusOnly": "true"}
        )
        vms = []
        image_properties = {}
        for discovered_vm in vm_list:
            vm_with_status = find_vm(vm_list_with_status, discovered_vm.id)
            vm = {}
            vm["id"] = discovered_vm.vm_id
            vm["name"] = discovered_vm.name
            vm["region"] = discovered_vm.location
            vm["azure_marketplace_image"] = is_marketplace_image(discovered_vm)
            vm["resourceGroup"] = resource_group(discovered_vm)
            vm["running"] = is_running(vm_with_status)
            vm["is_encrypted"] = is_encrypted(discovered_vm)
            vm["image"] = vars(discovered_vm.storage_profile.image_reference)
            image_properties = get_image_properties(
                cm_client, image_properties, discovered_vm
            )
            vm["image_properties"] = image_properties
            vm["architecture"] = architecture(image_properties)
            vm["license_type"] = discovered_vm.license_type
            vm["vm_size"] = discovered_vm.hardware_profile.vm_size
            vm["inspection_json"] = inspection_json(discovered_vm)
            vm["hardware_profile"] = vars(discovered_vm.hardware_profile)
            vm["storage_profile"] = vars(discovered_vm.storage_profile)
            vm["os_profile"] = vars(discovered_vm.os_profile)
            vm["network_profile"] = vars(discovered_vm.network_profile)
            vm["diagnostics_profile"] = vars(discovered_vm.diagnostics_profile)
            vm["os_disk"] = vars(discovered_vm.storage_profile.os_disk)
            vm["managed_disk"] = None
            if (
                discovered_vm.storage_profile.os_disk
                and discovered_vm.storage_profile.os_disk.managed_disk
            ):
                vm["managed_disk"] = vars(
                    discovered_vm.storage_profile.os_disk.managed_disk
                )
            vms.append(vm)
            return vms
    except ClientAuthenticationError:
        logger.error(
            _(
                "Could not discover vms for subscription %(subscription_id)s, "
                "Failed to authenticate a new client."
            ),
            {"subscription_id": azure_subscription_id},
        )
        return []


def find_vm(vm_list, vm_id):
    """Given the list of vms return the vm object matching the vm_id."""
    for vm in vm_list:
        if vm.id == vm_id:
            return vm
    return None


def get_image_properties(cm_client, image_properties, vm):
    """
    Given the vm, get additional image properties.

    Architecture of a disk image is not returned to us by default.
    We need to explicitely ask for additional properties via the
    expand parameter.

    {
      'additional_properties': {'properties': {'hyperVGeneration': 'V2',
                                               'architecture': 'x64',
                                               'replicaType': 'Managed',
                                               'replicaCount': 10}},
      'id': '/Subscriptions/c2b810d4-e83c-4df5-a728-f1301dd78561/'
            'Providers/Microsoft.Compute/Locations/eastus/'
            'Publishers/RedHat/ArtifactTypes/VMImage/Offers/RHEL/'
            'Skus/82gen2/Versions/8.2.2020050812',
      'name': '8.2.2020050812',
      'location': 'eastus',
      'tags': None,
      'extended_location': None
    }
    """
    image = vm.storage_profile.image_reference
    sku = image.sku
    if sku in image_properties.keys():
        return image_properties[sku]
    image_reference = vm.storage_profile.image_reference
    image_property = cm_client.virtual_machine_images.list(
        location=vm.location,
        publisher_name=image_reference.publisher,
        offer=image_reference.offer,
        skus=sku,
        expand="properties",
    )[0]
    image_properties[sku] = image_property
    return image_properties[sku]


def architecture(image_properties):
    """Return the architecture for the image properties specified."""
    return image_properties.additional_properties["properties"]["architecture"]


def is_marketplace_image(vm):
    """
    Return True if the vm's image is from the marketplace.

    As per the plan attribute of a Virtual Machine, defined here by its class
    https://docs.microsoft.com/en-us/python/api/azure-mgmt-compute/azure.mgmt.compute.v2017_03_30.models.plan?view=azure-python
    if defined, the image came from the marketplace.
    """
    return True if vm.plan else False


def inspection_json(vm):
    """
    Return the inspection for the vm.

    For now simply the json of the machine image
    """
    return json.dumps(vars(vm.storage_profile.image_reference))


def is_running(vm):
    """Return true if the vm specified has a PowerState/running state."""
    running = False
    if vm and vm.instance_view:
        for status in vm.instance_view.statuses:
            if status.code == "PowerState/running":
                running = True
                break
    return running


def is_encrypted(vm):
    """Return true if the vm specified is encrypted."""
    is_encrypted = True if vm.storage_profile.os_disk.encryption_settings else False
    return is_encrypted


def resource_group(vm):
    """Return the resourceGroup for the vm object."""
    return vm.id.split("/")[4]
