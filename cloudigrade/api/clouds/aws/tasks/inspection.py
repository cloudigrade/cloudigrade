"""Celery tasks related to the AWS image inspection process."""
import logging

import boto3
from django.conf import settings
from django.utils.translation import gettext as _

from api.clouds.aws.models import AwsMachineImage
from util import aws
from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.aws.tasks.launch_inspection_instance")
@aws.rewrap_aws_errors
def launch_inspection_instance(ami_id, snapshot_copy_id):
    """
    Run an inspection instance.

    Args:
        ami_id(str): ID of the AMI being inspected
        snapshot_copy_id(str): ID of the AMI snapshot
    """
    # Check Snapshot
    ec2_resource = boto3.resource("ec2")
    snapshot_copy = ec2_resource.Snapshot(snapshot_copy_id)
    aws.check_snapshot_state(snapshot_copy)

    # Update Status
    try:
        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
    except AwsMachineImage.DoesNotExist:
        logger.info(
            _(
                "%(label)s AMI ID %(ami_id)s is no longer known to us, "
                "cancelling launch of this inspection."
            ),
            {
                "label": "launch_inspection_instance",
                "ami_id": ami_id,
            },
        )
        return

    machine_image = aws_image.machine_image.get()
    machine_image.status = machine_image.INSPECTING
    machine_image.save()

    # Run Inspection
    cloud_init_script = _build_cloud_init_script(ami_id)
    logger.info(
        _("Launching inspection for AMI %(ami_id)s"),
        {
            "ami_id": ami_id,
        },
    )
    ec2_client = boto3.client("ec2")
    ec2_client.run_instances(
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/xvdbb",
                "Ebs": {
                    "DeleteOnTermination": True,
                    "SnapshotId": snapshot_copy_id,
                    "VolumeType": "gp2",
                    "Encrypted": False,
                },
            },
        ],
        InstanceInitiatedShutdownBehavior="terminate",
        LaunchTemplate={
            "LaunchTemplateName": f"cloudigrade-lt-{settings.CLOUDIGRADE_ENVIRONMENT}"
        },
        MaxCount=1,
        MinCount=1,
        UserData=cloud_init_script,
    )


def _build_cloud_init_script(ami_id):
    """
    Build a cloud init script that'll run the inspection.

    Args:
        ami_id(str): ID of the AMI being inspected

    Returns (str): Complete cloud init script.

    """
    houndigrade_image = (
        f"{settings.HOUNDIGRADE_ECS_IMAGE_NAME}:{settings.HOUNDIGRADE_ECS_IMAGE_TAG}"
    )

    cloud_init_script = f"""Content-Type: multipart/mixed; boundary="//"
MIME-Version: 1.0

--//
Content-Type: text/cloud-config; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="cloud-config.txt"

#cloud-config
cloud_final_modules:
- [scripts-user, always]

--//
Content-Type: text/x-shellscript; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit
Content-Disposition: attachment; filename="userdata.txt"

#!/bin/bash

docker pull docker pull {houndigrade_image}
docker run \
    --mount type=bind,source=/dev,target=/dev \
    --privileged --rm \
    -e AWS_ACCESS_KEY_ID={settings.AWS_SQS_ACCESS_KEY_ID} \
    -e AWS_DEFAULT_REGION={settings.AWS_SQS_REGION} \
    -e AWS_SECRET_ACCESS_KEY={settings.AWS_SQS_SECRET_ACCESS_KEY} \
    -e EXCHANGE_NAME={settings.HOUNDIGRADE_EXCHANGE_NAME} \
    -e HOUNDIGRADE_SENTRY_DSN={settings.HOUNDIGRADE_SENTRY_DSN} \
    -e HOUNDIGRADE_SENTRY_RELEASE={settings.HOUNDIGRADE_SENTRY_RELEASE} \
    -e HOUNDIGRADE_SENTRY_ENVIRONMENT={settings.HOUNDIGRADE_SENTRY_ENVIRONMENT} \
    -e RESULTS_QUEUE_NAME={settings.HOUNDIGRADE_RESULTS_QUEUE_NAME} \
    -e QUEUE_CONNECTION_URL={settings.AWS_SQS_URL} \
    {houndigrade_image} \
    -c aws \
    -t {ami_id} /dev/xvdbb

shutdown -h now

--//--
    """
    return cloud_init_script
