"""Process events and turn them into runs."""
import logging

from django.core.management.base import BaseCommand

from account.models import AwsInstanceEvent, Run
from account.reports import normalize_runs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Creates runs from existing events."""

    def handle(self, *args, **options):
        """Handle the command execution."""
        events = AwsInstanceEvent.objects.all()

        normalized_runs = normalize_runs(events)

        for index, normalized_run in enumerate(normalized_runs):
            logger.info('Processing run {} of {}'.format(
                index + 1, len(normalized_runs)))
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
