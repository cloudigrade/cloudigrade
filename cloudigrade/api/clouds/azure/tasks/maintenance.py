"""Celery tasks related to maintenance functions around Azure."""
import json
import logging

import bitmath
from azure.mgmt.compute import ComputeManagementClient
from django.db import transaction
from django.utils.translation import gettext as _

from api import AZURE_PROVIDER_STRING
from api.util import save_instance_type_definitions
from util import azure
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.azure.tasks.repopulate_azure_instance_mapping")
def repopulate_azure_instance_mapping():
    """
    Use the Azure Compute client to update the Azure instancetype lookup table.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    definitions = _fetch_azure_instance_type_definitions()
    with transaction.atomic():
        try:
            save_instance_type_definitions(definitions, AZURE_PROVIDER_STRING)
        except Exception as e:
            logger.exception(
                _("Failed to save Azure instance definitions; rolling back.")
            )
            raise e
    logger.info(_("Finished saving Azure instance type definitions."))


def _fetch_azure_instance_type_definitions():
    """
    Fetch Azure instance type definitions from Azure Resource Sku API.

    Returns:
        dict: definitions dict of dicts where the outer key is the instance
        type name and the inner dict has keys memory, vcpu and json_definition.
        For example: {'r5.large': {'memory': 24.0, 'vcpu': 1, 'json_definition': {...}}}

    """
    compute_client = ComputeManagementClient(
        azure.get_cloudigrade_credentials(), azure.get_cloudigrade_subscription_id()
    )
    resource_skus = compute_client.resource_skus.list()
    instances = {}
    for resource_sku in resource_skus:
        # We can not filter by resource_type, so we just ignore anything that's not a vm
        if resource_sku.resource_type != "virtualMachines":
            continue

        # Extract vcpu and memory data from the capabilities list
        vcpu = None
        memory = None
        for capability in resource_sku.capabilities:
            vcpu = capability.value if capability.name == "vCPUs" else vcpu
            if capability.name == "MemoryGB":
                # Azure reports memory in GB, here we convert
                # GB values to MiB values to keep our instance
                # definitions consistent across clouds
                memory = bitmath.GB(capability.value).to_MiB()

        instances[resource_sku.name] = {
            "memory": memory,
            "vcpu": vcpu,
            "json_definition": json.dumps(resource_sku, default=lambda x: x.__dict__),
        }

    return instances
