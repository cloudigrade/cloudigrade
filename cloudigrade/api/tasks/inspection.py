"""Tasks for various inspection operations."""
import json
import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _

from api.clouds.aws.tasks import CLOUD_KEY, CLOUD_TYPE_AWS
from api.clouds.aws.util import (
    persist_aws_inspection_cluster_results,
    start_image_inspection,
)
from api.models import MachineImage
from util import aws
from util.misc import get_now

logger = logging.getLogger(__name__)


@shared_task(name="api.tasks.persist_inspection_cluster_results_task")
@aws.rewrap_aws_errors
def persist_inspection_cluster_results_task():
    """
    Task to run periodically and read houndigrade messages.

    Returns:
        tuple[list, list]: lists of messages that succeeded and failed to process

    """
    queue_url = aws.get_sqs_queue_url(settings.HOUNDIGRADE_RESULTS_QUEUE_NAME)
    successes, failures = [], []
    for message in aws.yield_messages_from_queue(
        queue_url, settings.AWS_SQS_MAX_HOUNDI_YIELD_COUNT
    ):
        logger.info(
            _('Processing inspection results notification with id "%s"'),
            message.message_id,
        )

        inspection_results = _fetch_inspection_results(message)
        for inspection_result in inspection_results:
            if inspection_result.get(CLOUD_KEY) == CLOUD_TYPE_AWS:
                try:
                    persist_aws_inspection_cluster_results(inspection_result)
                except Exception as e:
                    logger.exception(_("Unexpected error in result processing: %s"), e)
                    logger.debug(_("Failed message body is: %s"), message.body)
                    failures.append(message)
                    continue

                logger.info(
                    _("Successfully processed message id %s; deleting from queue."),
                    message.message_id,
                )
                aws.delete_messages_from_queue(queue_url, [message])
                successes.append(message)
            else:
                logger.error(
                    _('Unsupported cloud type: "%s"'), inspection_result.get(CLOUD_KEY)
                )
                failures.append(message)

    if not (successes or failures):
        logger.info("No inspection results found.")

    return successes, failures


def _fetch_inspection_results(message):
    """
    Fetch inspection results from S3 bucket via key specified in message.

    Returns:
        list(json): list of json result(s) retrieved.
    """
    logs = []
    inspection_results = []
    extracted_messages = aws.extract_sqs_message(message)
    for extracted_message in extracted_messages:
        bucket = extracted_message["bucket"]["name"]
        key = extracted_message["object"]["key"]
        raw_content = aws.get_object_content_from_s3(bucket, key)
        content = json.loads(raw_content)
        logs.append((content, bucket, key))
        inspection_results.append(content)
        logger.info(
            _(
                "Read Houndigrade Inspection Result file "
                "from bucket %(bucket)s object key %(key)s"
            ),
            {"bucket": bucket, "key": key},
        )
    return inspection_results


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
