"""Spawn a bunch of accounts, images, and powered-on instances."""
import datetime
from random import choice, random, randrange

from dateutil import tz
from dateutil.parser import parse as dateutil_parse
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from account.models import InstanceEvent
from account.tests import helper as account_helper
from util.tests import helper as util_helper


class Command(BaseCommand):
    """Spawn a bunch of accounts, images, and powered-on instances."""

    help = _('Spawn a bunch of accounts, images, and powered-on instances. '
             'This command is intended only for generating "dummy" test data '
             'in non-production environments.')

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument('user_id', type=str,
                            help=_('ID of the user who owns the accounts'))
        parser.add_argument('since', type=dateutil_parse,
                            help=_('earliest time instances may be started'))
        parser.add_argument('--account_count', type=int, default=4)
        parser.add_argument('--image_count', type=int, default=100)
        parser.add_argument('--instance_count', type=int, default=5000)
        parser.add_argument('--ocp_chance', type=float, default=0.5,
                            help=_('chance of new image finding OCP (0-1)'))
        parser.add_argument('--rhel_chance', type=float, default=0.5,
                            help=_('chance of new image finding RHEL (0-1)'))
        parser.add_argument('--other_owner_chance', type=float, default=0.5,
                            help=_('chance of new image not belonging to one '
                                   'of this user\'s accounts (0-1)'))

    def confirm(self, options):
        """Seek manual confirmation before proceeding."""
        question = _('Are you SURE you want to proceed? This will generate '
                     'data representing:\n'
                     '- {account_count} AWS account(s)\n'
                     '- {image_count} AWS image(s)\n'
                     '- {instance_count} AWS instance(s)\n'
                     '- {instance_count} power-on event(s) since {since}\n\n'
                     'Enter YES to proceed:').format(**options)
        result = input('{} '.format(question))
        if result != 'YES':
            self.stdout.write(_('Aborting.'))
            return False
        return True

    def handle(self, *args, **options):
        """Handle the command execution."""
        if not self.confirm(options):
            return False

        since = options['since']
        if not since.tzinfo:
            since = since.replace(
                tzinfo=tz.tzutc()
            )
        now = datetime.datetime.now(tz=since.tzinfo)
        seconds = int(datetime.timedelta.total_seconds(now - since))

        user = User.objects.get(pk=options['user_id'])

        accounts = [
            account_helper.generate_aws_account(user=user)
            for __ in range(options['account_count'])
        ]
        self.stdout.write(_('Created {} account(s)').format(len(accounts)))

        images = [
            account_helper.generate_aws_image(
                owner_aws_account_id=choice(accounts).aws_account_id
                if random() < options['other_owner_chance']
                else util_helper.generate_dummy_aws_account_id(),
                rhel_detected=random() < options['rhel_chance'],
                openshift_detected=random() < options['ocp_chance'],
            )
            for __ in range(options['image_count'])
        ]
        self.stdout.write(_('Created {} images(s)').format(len(images)))

        instances = [
            account_helper.generate_aws_instance(
                account=choice(accounts),
            )
            for __ in range(options['instance_count'])
        ]
        self.stdout.write(_('Created {} instances(s)').format(len(instances)))

        for instance in instances:
            account_helper.generate_single_aws_instance_event(
                instance=instance,
                occurred_at=since + datetime.timedelta(
                    seconds=randrange(seconds)),
                ec2_ami_id=choice(images).ec2_ami_id,
                event_type=InstanceEvent.TYPE.power_on,
            )
        self.stdout.write(_('Created {} events(s)').format(len(instances)))
