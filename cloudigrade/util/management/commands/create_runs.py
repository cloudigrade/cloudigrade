"""Process events and turn them into runs."""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from tqdm import tqdm

from api.models import ConcurrentUsage, Instance, InstanceEvent, Run
from api.util import calculate_max_concurrent_usage_from_runs, recalculate_runs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Creates runs from existing events."""

    def confirm(self, runs_count, concurrent_usage_count):
        """Seek manual confirmation before proceeding."""
        question = (
            "This will destroy {} Runs and {} Concurrent Usage objects. "
            "Are you SURE you want to proceed?"
        ).format(runs_count, concurrent_usage_count)
        result = input("{} [Y/n] ".format(question))
        if result.lower() != "y":
            self.stdout.write("Aborting.")
            return False
        return True

    def add_arguments(self, parser):
        """Add a command-line argument to skip confirmation prompt."""
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="automatically confirm destructive operation",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        """Handle the command execution."""
        all_runs = Run.objects.all()
        runs_count = all_runs.count()
        all_concurrent_usage = ConcurrentUsage.objects.all()
        concurrent_usage_count = all_concurrent_usage.count()
        if runs_count > 0 or concurrent_usage_count > 0:
            self.stdout.write(
                "Found {} existing Runs and {} Concurrent Usage "
                "objects.".format(runs_count, concurrent_usage_count)
            )
            if not options.get("confirm") and not self.confirm(
                runs_count, concurrent_usage_count
            ):
                return False
            all_runs.delete()
            logger.info("Deleted all Run objects.")
            all_concurrent_usage.delete()
            logger.info("Deleted all ConcurrentUsage objects.")

        runs = []
        for instance in tqdm(Instance.objects.all(), desc="Runs for instances"):
            if (
                event := InstanceEvent.objects.filter(
                    instance=instance, event_type=InstanceEvent.TYPE.power_on
                )
                .order_by("occurred_at")
                .first()
            ):
                # Find the earliest power_on event for this instance (if one exists),
                # and use that as the starting point for recalculating runs.
                # The event_type filter is a slight premature optimization here.
                # Alternatively we could just look for *any* event, but if an instance
                # only has power_off events, for example, we ultimately create no runs.
                runs.extend(recalculate_runs(event))

        logger.info("Created {} runs.".format(len(runs)))
        logger.info("Generating concurrent usage calculation tasks.")
        calculate_max_concurrent_usage_from_runs(runs)
        logger.info("Finished generating concurrent usage calculation tasks.")
        logger.info("Reminder: run the Celery worker to calculate concurrent usages!")
