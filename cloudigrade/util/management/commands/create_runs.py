"""Process events and turn them into runs."""
import logging

from django.core.management.base import BaseCommand
from tqdm import tqdm

from account.models import AwsInstance, AwsInstanceEvent, Run
from account.reports import normalize_runs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Creates runs from existing events."""

    def confirm(self, runs_count):
        """Seek manual confirmation before proceeding."""
        question = (
            'This will destroy {} Runs. Are you SURE you want to proceed?'
        ).format(runs_count)
        result = input('{} [Y/n] '.format(question))
        if result.lower() != 'y':
            self.stdout.write('Aborting.')
            return False
        return True

    def handle(self, *args, **options):
        """Handle the command execution."""
        all_runs = Run.objects.all()
        if not self.confirm(all_runs.count()):
            return False
        all_runs.delete()

        runs_created = 0
        for instance in tqdm(
            AwsInstance.objects.all(), desc='instances'
        ):
            events = AwsInstanceEvent.objects.filter(instance=instance)

            normalized_runs = normalize_runs(events)

            for normalized_run in tqdm(
                normalized_runs,
                desc='runs for {}'.format(instance),
            ):
                runs_created += 1
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

        logger.info('Created {} runs.'.format(runs_created))
