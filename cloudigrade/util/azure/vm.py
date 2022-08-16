"""Utility methods to handle azure virtual machines."""
import logging

from azure.core.exceptions import ClientAuthenticationError
from azure.mgmt.compute import ComputeManagementClient
from django.utils.translation import gettext as _

from util import azure

logger = logging.getLogger(__name__)


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
        for discovered_vm in vm_list:
            vm_with_status = find_vm(vm_list_with_status, discovered_vm.id)
            vm = {}
            vm["id"] = discovered_vm.id
            vm["name"] = discovered_vm.name
            vm["resourceGroup"] = resource_group(discovered_vm)
            vm["running"] = is_running(vm_with_status)
            if vm_with_status and vm_with_status.instance_view:
                vm["instance_view"] = vars(vm_with_status.instance_view)
            vm["license_type"] = discovered_vm.license_type
            vm["vm_size"] = discovered_vm.hardware_profile.vm_size
            vm["hardware_profile"] = vars(discovered_vm.hardware_profile)
            vm["os_disk"] = vars(discovered_vm.storage_profile.os_disk)
            vm["image"] = vars(discovered_vm.storage_profile.image_reference)
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


def is_running(vm):
    """Return true if the vm specified has a PowerState/running state."""
    running = False
    if vm and vm.instance_view:
        for status in vm.instance_view.statuses:
            if status.code == "PowerState/running":
                running = True
                break
    return running


def resource_group(vm):
    """Return the resourceGroup for the vm object."""
    return vm.id.split("/")[4]
