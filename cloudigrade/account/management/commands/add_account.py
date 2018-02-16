"""Management command for storing AWS ARN credentials in the database."""
import collections

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from account.models import Account, Instance, InstanceEvent
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

        if aws.verify_account_access(arn):
            running_instances_data = aws.get_running_instances(arn)
            saved_instances = collections.defaultdict(list)

            with transaction.atomic():
                account = Account(account_arn=arn, account_id=account_id)
                account.save()

                for region, instances in running_instances_data.items():
                    for instance_data in instances:
                        instance, __ = Instance.objects.get_or_create(
                            account=account,
                            ec2_instance_id=instance_data['InstanceId'],
                            region=region,
                        )
                        event = InstanceEvent(
                            instance=instance,
                            event_type=InstanceEvent.TYPE.power_on,
                            occurred_at=timezone.now(),
                            subnet=instance_data['SubnetId'],
                            ec2_ami_id=instance_data['ImageId'],
                        )
                        event.save()
                        saved_instances[region].append(instance)

            self.stdout.write(self.style.SUCCESS(_('ARN Info Stored')))
            self.stdout.write(_(f'Running instances: {saved_instances}'))
        else:
            msg = 'Account verification failed. ARN Info Not Stored'
            self.stdout.write(self.style.WARNING(_(msg)))
