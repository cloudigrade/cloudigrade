"""Ensure SQS queues are correctly configured for cloudigrade."""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from util import aws

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Ensure SQS queues are correctly configured for cloudigrade."""

    help = _("Ensures SQS queues are correctly configured for cloudigrade.")

    queue_names = [
        "{0}ready_volumes".format(settings.AWS_NAME_PREFIX),
        settings.AWS_CLOUDTRAIL_EVENT_QUEUE_NAME,
    ]

    def handle(self, *args, **options):
        """Handle the command execution."""
        for queue_name in self.queue_names:
            self.stdout.write('Configuring SQS queue "{}"'.format(queue_name))
            queue_url = aws.get_sqs_queue_url(queue_name)
            try:
                aws.ensure_queue_has_dlq(queue_name, queue_url)
            except:  # noqa: E722
                logger.error(
                    _(
                        "Failed to configure queue %(name)s at %(url)s. "
                        "Please verify that a queue exists in this location. "
                        "We may not create this queue automatically!"
                    ),
                    {"name": queue_name, "url": queue_url},
                )
                raise
        aws.set_visibility_timeout(
            settings.AWS_CLOUDTRAIL_EVENT_QUEUE_NAME,
            settings.AWS_CLOUDTRAIL_EVENT_QUEUE_VISIBILITY_TIMEOUT,
        )
