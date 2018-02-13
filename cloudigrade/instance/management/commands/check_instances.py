"""Management command for checking currently-running AWS EC2 instances."""
import logging

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from util import aws

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Command to display a list of running instances for a given ARN.

    Example usage:

        ARN="arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274"
        python manage.py check_instances $ARN
    """

    help = _('Display a list of running instances for a given ARN.')

    def add_arguments(self, parser):
        """Add required arn argument for use by this command."""
        parser.add_argument(dest='arn', help=_('the arn to access'))

    def handle(self, *args, **options):
        """Handle command to display a list of running instances."""
        arn = options['arn']
        found_instances = aws.get_running_instances(arn)
        self.stdout.write(_(f'Instances found include: {found_instances}'))
