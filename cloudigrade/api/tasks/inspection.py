"""Tasks for various inspection operations."""
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from api.clouds.aws.util import (
    start_image_inspection,
)
from api.models import MachineImage
from util.misc import get_now

logger = logging.getLogger(__name__)


@shared_task(name="api.tasks.persist_inspection_cluster_results_task")
def persist_inspection_cluster_results_task():
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.
    return False


@shared_task(name="api.tasks.inspect_pending_images")
@transaction.atomic
def inspect_pending_images():
    """
    (Re)start inspection of images in PENDING, PREPARING, or INSPECTING status.

    This generally should not be necessary for most images, but if an image
    inspection fails to proceed normally, this function will attempt to run it
    through inspection again.

    This function runs atomically in a transaction to protect against the risk
    of it being called multiple times simultaneously which could result in the
    same image being found and getting multiple inspection tasks.
    """
    updated_since = get_now() - timedelta(
        seconds=settings.INSPECT_PENDING_IMAGES_MIN_AGE
    )
    restartable_statuses = [
        MachineImage.PENDING,
        MachineImage.PREPARING,
        MachineImage.INSPECTING,
    ]
    images = MachineImage.objects.filter(
        status__in=restartable_statuses,
        instance__aws_instance__region__isnull=False,
        updated_at__lt=updated_since,
    ).distinct()
    logger.info(
        _(
            "Found %(number)s images for inspection that have not updated "
            "since %(updated_time)s"
        ),
        {"number": images.count(), "updated_time": updated_since},
    )

    for image in images:
        instance = image.instance_set.filter(aws_instance__region__isnull=False).first()
        arn = instance.cloud_account.content_object.account_arn
        ami_id = image.content_object.ec2_ami_id
        region = instance.content_object.region
        start_image_inspection(arn, ami_id, region)
