"""Management command for analyzing AWS CloutTrail Logs."""
import collections
import datetime
import json

from dateutil import tz
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext as _

from account.models import Account, Instance, InstanceEvent
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
        extracted_messages = []
        instances = {}

        # Get messages off of an SQS queue
        messages = aws.receive_message_from_queue(queue_url)

        # Parse the SQS messages to get S3 object locations
        for message in messages:
            extracted_messages.extend(aws.extract_sqs_message(message))

        # Grab the object contents from S3
        for extracted_message in extracted_messages:
            bucket = extracted_message['bucket']['name']
            key = extracted_message['object']['key']
            logs.append(aws.get_object_content_from_s3(bucket, key))

        # Parse logs for on/off events
        for log in logs:
            if log:
                instances = self._parse_log_for_ec2_events(log)

        if instances:
            self._save_instances_and_events(instances)
            result = _('Saved instances and/or events to the DB.')
            self.stdout.write(result)
        else:
            result = _('No instances or events to save to the DB.')
            self.stdout.write(result)

        aws.delete_message_from_queue(queue_url, messages)

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
            'RunInstances': InstanceEvent.TYPE.power_on,
            'StartInstances': InstanceEvent.TYPE.power_on,
            'StopInstances': InstanceEvent.TYPE.power_off,
            'TerminateInstances': InstanceEvent.TYPE.power_off
        }
        instances = collections.defaultdict(dict)
        log = json.loads(log)

        # Each record is a single API call, but each call can
        # be made against multiple EC2 instances
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

            # Collect the EC2 instances the API was called on
            for item in ec2_info:
                instance_id = item.get('instanceId')
                instances[instance_id]['account_id'] = account_id
                instances[instance_id]['region'] = region

                event = self._build_instance_event(account_id, region, item)
                # Event type and time are the same for each instance
                event['event_type'] = event_type
                event['occurred_at'] = occured_at

                if instances[instance_id].get('events'):
                    instances[instance_id]['events'].append(event)
                else:
                    instances[instance_id]['events'] = [event]

        return dict(instances)

    def _build_instance_event(self, account_id, region, log_record):
        """
        Return critical data for an instance on/off event.

        Args:
            account_id (str): The account_id the instance belongs to.
            region (str): The AWS region the instance resides in.
            log_record (str): The instance specific data from the log record.

        Returns:
            dict: EC2 instance data for the event.

        """
        ec2_ami_id = log_record.get('imageId')
        instance_id = log_record.get('instanceId')
        instance_type = log_record.get('instanceType')
        subnet = log_record.get('subnetId')

        if subnet is None \
                or ec2_ami_id is None \
                or instance_type is None:
            account = Account.objects.get(account_id=account_id)
            session = aws.get_session(account.account_arn, region)
            instance = aws.get_ec2_instance(session, instance_id)
            subnet = instance.subnet_id
            ec2_ami_id = instance.image_id
            instance_type = instance.instance_type

        return {'subnet': subnet,
                'ec2_ami_id': ec2_ami_id,
                'instance_type': instance_type}

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

    @transaction.atomic
    def _save_instances_and_events(self, instances):
        """
        Save instances and on/off events to the DB.

        Args:
            instances (dict): Instance data, including a list of events.

        """
        for instance_id, instance_dict in instances.items():
            account_id = instance_dict['account_id']
            # TODO: Don't pull the same account record from the
            #       DB multiple times. Consider caching.
            account = Account.objects.get(account_id=account_id)
            instance, __ = Instance.objects.get_or_create(
                account=account,
                ec2_instance_id=instance_id,
                region=instance_dict['region'],
            )
            for event in instance_dict['events']:
                occurred_at_dt = datetime.datetime.strptime(
                    event['occurred_at'], '%Y-%m-%dT%H:%M:%SZ'
                ).replace(tzinfo=tz.tzutc())
                InstanceEvent.objects.create(
                    instance=instance,
                    event_type=event['event_type'],
                    occurred_at=occurred_at_dt,
                    subnet=event['subnet'],
                    ec2_ami_id=event['ec2_ami_id'],
                    instance_type=event['instance_type'],
                )
