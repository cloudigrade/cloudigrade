"""Process events and turn them into runs."""
from django.core.management.base import BaseCommand
from tqdm import tqdm

from account.models import AwsInstance, AwsInstanceEvent, Run
from account.reports import normalize_runs


class Command(BaseCommand):
    """Creates runs from existing events."""

    def handle(self, *args, **options):
        """Handle the command execution."""
        for instance in tqdm(AwsInstance.objects.all(), desc='instances'):
            events = AwsInstanceEvent.objects.filter(instance=instance)

            normalized_runs = normalize_runs(events)

            for normalized_run in tqdm(
                normalized_runs, desc='runs for {}'.format(instance)
            ):
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
