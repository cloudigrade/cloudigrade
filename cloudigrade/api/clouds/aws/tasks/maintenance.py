"""Celery tasks related to maintenance functions around AWS."""
import json
import logging

import boto3
from django.db import transaction
from django.utils.translation import gettext as _

from api import AWS_PROVIDER_STRING
from api.util import save_instance_type_definitions
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.aws.tasks.repopulate_ec2_instance_mapping")
def repopulate_ec2_instance_mapping():
    """
    Use the Boto3 pricing client to update the EC2 instancetype lookup table.

    Returns:
        None: Run as an asynchronous Celery task.

    """
    definitions = _fetch_ec2_instance_type_definitions()
    with transaction.atomic():
        try:
            save_instance_type_definitions(definitions, AWS_PROVIDER_STRING)
        except Exception as e:
            logger.exception(
                _("Failed to save EC2 instance definitions; rolling back.")
            )
            raise e
    logger.info(_("Finished saving AWS EC2 instance type definitions."))


def _fetch_ec2_instance_type_definitions():
    """
    Fetch EC2 instance type definitions from AWS Pricing API.

    Returns:
        dict: definitions dict of dicts where the outer key is the instance
        type name and the inner dict has keys memory, vcpu and json_definition.
        For example: {'r5.large': {'memory': 24.0, 'vcpu': 1, 'json_definition': {...}}}

    """
    client = boto3.client("ec2")
    regions = [region["RegionName"] for region in client.describe_regions()["Regions"]]

    instances = {}
    for region in regions:
        client = boto3.client("ec2", region_name=region)
        paginator = client.get_paginator("describe_instance_types")
        page_iterator = paginator.paginate()
        logger.info(_("Getting AWS EC2 instance type information."))
        for page in page_iterator:
            for instance in page["InstanceTypes"]:
                try:
                    instances[instance["InstanceType"]] = {
                        "memory": instance.get("MemoryInfo").get("SizeInMiB", 0),
                        "vcpu": instance.get("VCpuInfo").get("DefaultVCpus", 0),
                        "json_definition": json.dumps(instance),
                    }
                except ValueError:
                    logger.error(
                        _(
                            "Could not fetch EC2 definition for instance-type "
                            "%(instance_type)s, memory %(memory)s, vcpu %(vcpu)s."
                        ),
                        {
                            "instance_type": instance["InstanceType"],
                            "memory": instance.get("MemoryInfo").get("SizeInMiB", 0),
                            "vcpu": instance.get("VCpuInfo").get("DefaultVCpus", 0),
                        },
                    )

    return instances
