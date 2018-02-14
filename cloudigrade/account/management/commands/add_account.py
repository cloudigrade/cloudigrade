"""Management command for storing AWS ARN credentials in the database."""
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from account.models import Account
from util import aws


class Command(BaseCommand):
    """Command to store an Amazon ARN in the database.

    This command has the side-effect of also talking to Amazon to fetch and
    display a list of currently running EC2 instances visible to the ARN.

    Example usage:

        ARN="arn:aws:iam::518028203513:role/grant_cloudi_to_372779871274"
        python manage.py add_account $ARN
    """

    help = _('Stores AWS IAM Role and displays list of its running instances')

    def add_arguments(self, parser):
        """Require an ARN to be provided."""
        parser.add_argument('arn', help=_('Granted Role ARN'))

    def handle(self, *args, **options):
        """Extract the account id from the ARN and save both to database."""
        arn = options['arn']
        account_id = aws.extract_account_id_from_arn(arn)

        is_verified = aws.verify_account_access(arn)
        if is_verified:
            found_instances = aws.get_running_instances(arn)
            Account(account_arn=options['arn'], account_id=account_id).save()

            self.stdout.write(self.style.SUCCESS(_('ARN Info Stored')))
            self.stdout.write(_(f'Instances found include: {found_instances}'))
        else:
            self.stdout.write(self.style.WARNING(_('ARN Info Not Stored')))
