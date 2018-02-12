"""Management command for checking currently-running AWS EC2 instances."""
import collections
import logging

import boto3
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from util import aws

logger = logging.getLogger(__name__)


def get_running_instances(arn):
    """
    Find all running EC2 instances visible to the given ARN.

    Args:
        arn: Amazon Resource Name to use for assuming a role.

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.

    """
    credentials = aws.get_credentials_for_arn(arn)
    found_instances = collections.defaultdict(list)

    for region_name in aws.get_regions():
        role_session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=region_name,
        )

        ec2 = role_session.client('ec2')
        logger.debug(_(f'Describing instances in {region_name} for {arn}'))
        instances = ec2.describe_instances()
        for reservation in instances.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                found_instances[region_name].append(instance['InstanceId'])

    return dict(found_instances)


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
        found_instances = get_running_instances(arn)
        self.stdout.write(_(f'Instances found include: {found_instances}'))
