"""Process events and turn them into runs."""
import logging

from django.core.management.base import BaseCommand

from account.models import AwsInstanceEvent, Run, AwsInstance
from account.reports import normalize_runs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Creates runs from existing events."""

    def handle(self, *args, **options):
        """Handle the command execution."""
        for instance in AwsInstance.objects.all():
            logger.info('Processing events for instance {}'.format(instance))
            events = AwsInstanceEvent.objects.filter(instance=instance)

            normalized_runs = normalize_runs(events)

            for index, normalized_run in enumerate(normalized_runs):
                logger.info(
                    'Processing run {} of {}'.format(
                        index + 1, len(normalized_runs)
                    )
                )
                run = Run(
                    start_time=normalized_run.start_time,
                    end_time=normalized_run.end_time,
                    machineimage_id=normalized_run.image_id,
                    instance_id=normalized_run.instance_id,
                    instance_type=normalized_run.instance_type,
                    memory=normalized_run.instance_memory,
                    vcpu=normalized_run.instance_vcpu,
                )
                run.save()
