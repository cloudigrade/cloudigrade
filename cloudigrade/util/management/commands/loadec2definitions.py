"""
Trigger the async task to load EC2 instance definitions.

Note:
    Unless `--force` flag is given, this task checks if any definitions already
    exist, and it will only call the task if none are found.
"""
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from api import AWS_PROVIDER_STRING
from api.clouds.aws import tasks
from api.models import InstanceDefinition


class Command(BaseCommand):
    """Trigger the async task to load EC2 instance definitions."""

    help = _("Load AWS EC2 instance definitions if none are present.")

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "--force",
            action="store_true",
            help=_("force load definitions even if some are already present"),
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        if (
            not options["force"]
            and InstanceDefinition.objects.filter(
                cloud_type=AWS_PROVIDER_STRING
            ).exists()
        ):
            self.stdout.write(
                _("Nothing to do. EC2 instance definitions already exist.")
            )
            return
        # TODO: launch task to populate azure instance definitions
        tasks.repopulate_ec2_instance_mapping.delay()
        self.stdout.write(_("Async task launched to load EC2 instance definitions."))
