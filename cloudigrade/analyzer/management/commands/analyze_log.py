"""Management command for analyzing AWS CloutTrail Logs."""
import json

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

# from account.models import Account, Instance, InstanceEvent
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
        """Require an AWS SQS queue URL."""
        parser.add_argument('queue_url', help=_('AWS SQS Queue URL'))

    def handle(self, *args, **options):
        """Extract the account id from the ARN and save both to database."""
        queue_url = options['queue_url']

        logs = []
        parsed_messages = []

        # Get messages off of an SQS queue
        messages = aws.receive_message_from_queue(queue_url)

        # Parse the SQS messages to get S3 object locations
        for message in messages:
            parsed_messages.extend(self._parse_sqs_message(message))

        # Grab the object contents from S3
        for parsed_message in parsed_messages:
            bucket = parsed_message[0]
            key = parsed_message[1]
            logs.append(aws.get_object_content_from_s3(bucket, key))

        # Parse logs for On/Off events
        for log in logs:
            print(self._parse_log_for_ec2_events(log))

        # TODO: Save the messages to the DB
        # TODO: If we haven't seen this instance before we'll
        #       need to run describe_instances on it.
        #       Start and stop requests don't have all the
        #       info we need.

        # aws.delete_message_from_queue(queue_url, messages)

    def _parse_sqs_message(self, message):
        parsed_records = []
        message_body = json.loads(message.body)
        for record in message_body.get('Records', []):
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            parsed_records.append((bucket_name, object_key))
        return parsed_records

    def _parse_log_for_ec2_events(self, log):
        ec2_event_map = {
            'RunInstances': 'power_on',
            'StartInstances': 'power_on',
            'StopInstances': 'power_off',
            'TerminateInstances': 'power_off'
        }
        instances = []
        instance_events = []
        log = json.loads(log)
        for record in log.get('Records', []):
            if record.get('eventSource') != 'ec2.amazonaws.com':
                continue
            # Currently we do not store events that have an error
            elif record.get('errorCode'):
                continue
            # Currently we only want power on/power off EC2 events
            elif record.get('eventName') not in ec2_event_map.keys():
                continue

            account_id = record.get('userIdentity', {}).get('accountId')
            event_type = ec2_event_map[record.get('eventName')]
            region = record.get('awsRegion')
            occured_at = record.get('eventTime')
            ec2_info = record.get('responseElements', {})\
                .get('instancesSet', {})\
                .get('items', [])

            for item in ec2_info:
                instance_id = item.get('instanceId')
                instance_type = item.get('instanceType')
                ec2_ami_id = item.get('imageId')
                subnet = item.get('subnetId')

                instances.append((account_id, instance_id, region))

                # Subnet, ec2_ami_id, and instance_type will be None
                # for start/stop events.
                instance_events.append(
                    (instance_id,
                     event_type,
                     occured_at,
                     subnet,
                     ec2_ami_id,
                     instance_type)
                )

            return list(set(instances)), instance_events
