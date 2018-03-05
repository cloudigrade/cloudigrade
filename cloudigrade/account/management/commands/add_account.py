"""Management command for storing AWS ARN credentials in the database."""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext as _

from account.models import Account
from account.util import create_initial_instance_events
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

        session = aws.get_session(arn)

        if aws.verify_account_access(session):
            instances_data = aws.get_running_instances(session)

            account = Account(account_arn=arn, account_id=account_id)
            with transaction.atomic():
                account.save()
                saved_instances = create_initial_instance_events(
                    account,
                    instances_data
                )

            self.stdout.write(self.style.SUCCESS(_('ARN Info Stored')))
            self.stdout.write(_(f'Running instances: {saved_instances}'))
        else:
            msg = 'Account verification failed. ARN Info Not Stored'
            self.stdout.write(self.style.WARNING(_(msg)))
