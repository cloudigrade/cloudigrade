"""Management command for storing AWS ARN credentials in the database."""
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from account.models import Account


class Command(BaseCommand):
    """Command to store an amazon ARN in the database."""

    help = _('Stores AWS IAM Role')

    def add_arguments(self, parser):
        """Require an ARN to be provided."""
        parser.add_argument('arn', help=_('Granted Role ARN'))

    def handle(self, *args, **options):
        """Extract the account id from the ARN and save both to database."""
        account_id = options['arn'].split(':')[4]
        Account(account_arn=options['arn'], account_id=account_id).save()
        self.stdout.write(self.style.SUCCESS(_('ARN Info Stored')))
