"""Management command for analyzing AWS CloutTrail Logs."""
import json

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

# from account.models import Account, Instance, InstanceEvent
from util import aws


class Command(BaseCommand):
    """Command to analyze EC2 events from AWS CloudTrail logs.

    Example usage:

        QUEUE_URL="https://sqs.us-east-1.amazonaws.com/372779871274/doppler_customer_1_test_bucket_cloudtrail_events"
        python manage.py analyze_log $QUEUE_URL
    """

    help = _('Analyzed AWS CloudTrail logs for EC2 on/off events.')

    def add_arguments(self, parser):
        """Require an AWS SQS queue URL."""
        parser.add_argument('queue_url', help=_('AWS SQS Queue URL'))

    def handle(self, *args, **options):
        """Read SQS Queue for log location, and parse log for events."""
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

        # Parse logs for on/off events
        for log in logs:
            if log is None or log == '':
                continue
            instances, instance_events = self._parse_log_for_ec2_events(log)
            result = 'Found instances: {i} and events {e}'.format(
                i=instances, e=instance_events)
            self.stdout.write(_(result))

        # TODO: Save the messages to the DB
        # TODO: If we haven't seen this instance before we'll
        #       need to run describe_instances on it.
        #       Start and stop requests don't have all the
        #       info we need.

        # aws.delete_message_from_queue(queue_url, messages)

    def _parse_sqs_message(self, message):
        """
        Parse SQS message for path to log in S3.

        Args:
            message (boto3.SQS.Message): The Message object.

        Returns:
            list(tuple): List of (bucket, key) log file locations in S3.

        """
        parsed_records = []
        message_body = json.loads(message.body)
        for record in message_body.get('Records', []):
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            parsed_records.append((bucket_name, object_key))
        return parsed_records

    def _parse_log_for_ec2_events(self, log):
        """
        Parse S3 log for EC2 on/off events.

        Args:
            log (string): The string contents of the log file.

        Returns:
            list(tuple): List of instance data seen in log.
            list(tuple): List of instance_event data seen in log.

        """
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
            if not self._is_on_off_event(record, ec2_event_map.keys()):
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

    def _is_on_off_event(self, record, valid_events):
        """
        Determine if a log event is an EC2 on/off event.

        Args:
            record (dict): The log record record.
            valid_events (list): Events considered to be on/off.

        Returns:
            bool: Whether the record contains an on/off event

        """
        if record.get('eventSource') != 'ec2.amazonaws.com':
            return False
        # Currently we do not store events that have an error
        elif record.get('errorCode'):
            return False
        # Currently we only want power on/power off EC2 events
        elif record.get('eventName') not in valid_events:
            return False
        else:
            return True
