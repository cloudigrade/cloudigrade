"""Seed a bunch of users, accounts, images, instances, and events."""
import datetime

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from account.tests import helper as account_helper
from util.tests import helper as util_helper


class Command(BaseCommand):
    """Spawn a bunch of accounts, images, and powered-on instances."""

    help = _('Seed a bunch of users, accounts, images, instances, and events. '
             'This command is intended only for generating "dummy" test data '
             'in non-production environments for use by integrade.')

    def handle(self, *args, **options):
        """Handle the command execution."""
        # Dates
        today = datetime.datetime.now()
        today = datetime.datetime(today.year, today.month, 1, 0, 0, 0, 0)
        two_years = today - datetime.timedelta(days=365 * 2)
        one_year = today - datetime.timedelta(days=365)
        one_year_minus_two_days = one_year + datetime.timedelta(days=2)
        one_year_minus_seven_days = one_year + datetime.timedelta(days=7)
        sixty_five_days = today - datetime.timedelta(days=65)
        fifty_five_days = today - datetime.timedelta(days=55)
        forty_five_days = today - datetime.timedelta(days=45)
        twenty_one_days = today - datetime.timedelta(days=21)
        seventeen_days = today - datetime.timedelta(days=17)
        fourteen_days = today - datetime.timedelta(days=14)
        twelve_days = today - datetime.timedelta(days=12)
        seven_days = today - datetime.timedelta(days=7)
        one_day = today - datetime.timedelta(days=1)
        twelve_hours = today - datetime.timedelta(hours=12)
        three_hours = today - datetime.timedelta(hours=3)
        one_hour = today - datetime.timedelta(hours=1)
        thirty_minutes = today - datetime.timedelta(minutes=30)

        # Generate AWS EC2 Definitions
        account_helper.generate_aws_ec2_definitions()

        # Users
        user1 = util_helper.generate_test_user(
            email='user1@example.com',
            password='user1@example.com',
            is_superuser=False,
        )
        user2 = util_helper.generate_test_user(
            email='user2@example.com',
            password='user2@example.com',
            is_superuser=False,
        )

        # Clounts
        user1clount1 = account_helper.generate_aws_account(
            user=user1,
            created_at=two_years,
            name='user1clount1'
        )
        user1clount2 = account_helper.generate_aws_account(
            user=user1,
            created_at=two_years,
            name='user1clount2'
        )

        user2clount1 = account_helper.generate_aws_account(
            user=user2,
            created_at=two_years,
            name='user2clount1'
        )
        user2clount2 = account_helper.generate_aws_account(
            user=user2,
            created_at=two_years,
            name='user2clount2'
        )
        user2clount3 = account_helper.generate_aws_account(
            user=user2,
            created_at=two_years,
            name='user2clount3hasAreallyLongNameFullOfExtraLetterssdfgiubqert'
        )

        # Images
        user1clount1image1 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user1clount1.aws_account_id),
        )

        user1clount2image1 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user1clount2.aws_account_id),
            rhel_detected=True,
            rhel_detected_certs=True,
            openshift_detected=True,
        )
        user1clount2image2 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user1clount2.aws_account_id),
            rhel_detected=True,
            rhel_detected_repos=True,
            rhel_detected_signed_packages=True,
        )
        user1clount2image3 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user1clount2.aws_account_id),
            rhel_detected=True,
            rhel_detected_certs=True,
            rhel_detected_repos=True,
            rhel_detected_release_files=True,
            rhel_detected_signed_packages=True,
        )

        user2clount1image1 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user2clount1.aws_account_id),
        )
        user2clount2image1 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user2clount1.aws_account_id),
            ec2_ami_id='ami-8f6ad3ef',
            openshift_detected=True,
        )
        user2clount3image1 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user2clount1.aws_account_id),
            is_cloud_access=True,
        )
        user2clount3image2 = account_helper.generate_aws_image(
            owner_aws_account_id=int(user2clount1.aws_account_id),
            is_marketplace=True,
        )

        # Instances
        # User 1 Clount 1
        user1clount1image1instance1 = account_helper.generate_aws_instance(
            account=user1clount1,
            image=user1clount1image1,
        )
        # User 1 Clount 2
        user1clount2image1instance1 = account_helper.generate_aws_instance(
            account=user1clount2,
            image=user1clount2image1,
        )
        user1clount2image2instance1 = account_helper.generate_aws_instance(
            account=user1clount2,
            image=user1clount2image2,
        )
        user1clount2image3instance1 = account_helper.generate_aws_instance(
            account=user1clount2,
            image=user1clount2image3,
        )

        # User 2 Clount1
        user2clount1image1instance1 = account_helper.generate_aws_instance(
            account=user2clount1,
            image=user2clount1image1,
        )
        user2clount1image1instance2 = account_helper.generate_aws_instance(
            account=user2clount1,
            image=user2clount1image1,
        )
        user2clount1image1instance3 = account_helper.generate_aws_instance(
            account=user2clount1,
            image=user2clount1image1,
        )
        # User 2 Clount 2
        user2clount2image1instance1 = account_helper.generate_aws_instance(
            account=user2clount2,
            image=user2clount2image1,
        )
        user2clount2image1instance2 = account_helper.generate_aws_instance(
            account=user2clount2,
            image=user2clount2image1,
        )
        # User 2 Clount 3
        user2clount3image1instance1 = account_helper.generate_aws_instance(
            account=user2clount3,
            image=user2clount3image1,
        )
        user2clount3image2instance1 = account_helper.generate_aws_instance(
            account=user2clount3,
            image=user2clount3image2,
        )

        # Events
        # User 1 Clount 1
        account_helper.generate_aws_instance_events(
            instance=user1clount1image1instance1,
            powered_times=[(twelve_hours, three_hours)],
            ec2_ami_id=user1clount1image1.ec2_ami_id,
        )
        # User 1 Clount 2
        account_helper.generate_aws_instance_events(
            instance=user1clount2image1instance1,
            powered_times=[(one_year, one_year_minus_two_days)],
            ec2_ami_id=user1clount2image1.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            instance=user1clount2image2instance1,
            powered_times=[(one_year, one_year_minus_seven_days)],
            ec2_ami_id=user1clount2image2.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            instance=user1clount2image3instance1,
            powered_times=[(one_year, one_year_minus_seven_days)],
            ec2_ami_id=user1clount2image3.ec2_ami_id,
        )
        # User 2 Clount 1
        account_helper.generate_aws_instance_events(
            instance=user2clount1image1instance1,
            powered_times=[(one_day, None)],
            ec2_ami_id=user2clount1image1.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            instance=user2clount1image1instance2,
            powered_times=[
                (twenty_one_days, fourteen_days), (twelve_days, seven_days)],
            ec2_ami_id=user2clount1image1.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            instance=user2clount1image1instance3,
            powered_times=[(seventeen_days, None)],
            ec2_ami_id=user2clount1image1.ec2_ami_id,
        )
        # User 2 Clount 2
        account_helper.generate_aws_instance_events(
            instance=user2clount2image1instance1,
            powered_times=[
                (fifty_five_days, forty_five_days),
                (one_day, None)],
            ec2_ami_id=user2clount2image1.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            instance=user2clount2image1instance2,
            powered_times=[
                (sixty_five_days, fifty_five_days),
                (forty_five_days, twenty_one_days),
                (twenty_one_days, fourteen_days),
                (twelve_days, None)],
            ec2_ami_id=user2clount2image1.ec2_ami_id,
        )
        # User 3 Clount 3
        account_helper.generate_aws_instance_events(
            instance=user2clount3image1instance1,
            powered_times=[(one_hour, thirty_minutes)],
            ec2_ami_id=user2clount3image1.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            instance=user2clount3image2instance1,
            powered_times=[(three_hours, thirty_minutes)],
            ec2_ami_id=user2clount3image2.ec2_ami_id,
        )

        call_command('create_runs', '--confirm')
