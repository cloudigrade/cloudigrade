"""Collection of tests for Analyzer management commands."""
import datetime
import json
import random
import uuid
from io import StringIO
from unittest.mock import patch

from dateutil import tz
from django.core.management import call_command
from django.test import TestCase
from django.utils.translation import gettext as _

from account.models import Instance, InstanceEvent
from account.tests import helper as account_helper
from analyzer.management.commands.analyze_log import aws
from util.tests import helper as util_helper


class AnalyzeLogTest(TestCase):
    """Analyze Log management command test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.mock_account_id = str(util_helper.generate_dummy_aws_account_id())
        self.mock_arn = util_helper.generate_dummy_arn(self.mock_account_id)
        self.mock_account = account_helper.generate_account(
            self.mock_arn, self.mock_account_id,
        )

    def test_command_output_success_ec2_attributes_included(self):
        """Test processing a CloudTrail log with all data included."""
        out = StringIO()
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_instance_id = str(uuid.uuid4())
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_event_type = 'RunInstances'
        now = datetime.datetime.utcnow()
        # Work around for sqlite handling of microseconds
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )
        mock_subnet = 'subnet-9000'
        mock_ec2_ami_id = str(uuid.uuid4())
        mock_instance_type = 't2.nano'

        mock_sqs_message_body = {
            'Records': [
                {
                    's3': {
                        'bucket': {
                            'name': 'test-bucket',
                        },
                        'object': {
                            'key': 'path/to/log/log.json.gz',
                        },
                    },
                }
            ]
        }
        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = {
            'Records': [
                {
                    'awsRegion': mock_region,
                    'eventName': mock_event_type,
                    'eventSource': 'ec2.amazonaws.com',
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventType': 'AwsApiCall',
                    'responseElements': {
                        'instancesSet': {
                            'items': [
                                {
                                    'imageId': mock_ec2_ami_id,
                                    'instanceId': mock_instance_id,
                                    'instanceType': mock_instance_type,
                                    'subnetId': mock_subnet
                                }
                            ]
                        },
                    },
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    }
                }
            ]
        }

        expected_out = _('Saved instances and/or events to the DB.')

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3, \
                patch.object(aws, 'delete_message_from_queue') as mock_del:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = json.dumps(mock_cloudtrail_log)
            mock_del.return_value = 'Success'

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue().strip()

        self.assertIn(actual_stdout, expected_out)

        instances = list(Instance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(InstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        for instance in instances:
            self.assertEqual(instance.account, self.mock_account)
            self.assertEqual(instance.ec2_instance_id, mock_instance_id)
            self.assertEqual(instance.region, mock_region)

        for event in instance_events:
            self.assertEqual(event.instance, instances[0])
            self.assertEqual(event.event_type, InstanceEvent.TYPE.power_on)
            self.assertEqual(event.occurred_at, mock_occurred_at)
            self.assertEqual(event.subnet, mock_subnet)
            self.assertEqual(event.ec2_ami_id, mock_ec2_ami_id)
            self.assertEqual(event.instance_type, mock_instance_type)

    def test_command_output_success_lookup_ec2_attributes(self):
        """Test processing a CloudTrail log with missing instance data."""
        out = StringIO()
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_instance_id = str(uuid.uuid4())
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_event_type = 'StartInstances'
        now = datetime.datetime.utcnow()
        # Work around for sqlite handling of microseconds
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )
        mock_subnet = 'subnet-9000'
        mock_ec2_ami_id = str(uuid.uuid4())
        mock_instance_type = 't2.nano'

        mock_instance = util_helper.generate_mock_ec2_instance(
            mock_instance_id, mock_ec2_ami_id, mock_subnet, None,
            mock_instance_type
        )

        mock_sqs_message_body = {
            'Records': [
                {
                    's3': {
                        'bucket': {
                            'name': 'test-bucket',
                        },
                        'object': {
                            'key': 'path/to/log/log.json.gz',
                        },
                    },
                }
            ]
        }
        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = {
            'Records': [
                {
                    'awsRegion': mock_region,
                    'eventName': mock_event_type,
                    'eventSource': 'ec2.amazonaws.com',
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventType': 'AwsApiCall',
                    'responseElements': {
                        'instancesSet': {
                            'items': [
                                {
                                    'imageId': None,
                                    'instanceId': mock_instance_id,
                                    'instanceType': None,
                                    'subnetId': None
                                }
                            ]
                        },
                    },
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    }
                }
            ]
        }

        expected_out = _('Saved instances and/or events to the DB.')

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3, \
                patch.object(aws, 'delete_message_from_queue') as mock_del, \
                patch.object(aws, 'get_session') as mock_session,\
                patch.object(aws, 'get_ec2_instance') as mock_ec2:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = json.dumps(mock_cloudtrail_log)
            mock_del.return_value = 'Success'
            mock_session.return_value = 'Session'
            mock_ec2.return_value = mock_instance

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue().strip()

        self.assertIn(actual_stdout, expected_out)

        instances = list(Instance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(InstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        for instance in instances:
            self.assertEqual(instance.account, self.mock_account)
            self.assertEqual(instance.ec2_instance_id, mock_instance_id)
            self.assertEqual(instance.region, mock_region)

        for event in instance_events:
            self.assertEqual(event.instance, instances[0])
            self.assertEqual(event.event_type, InstanceEvent.TYPE.power_on)
            self.assertEqual(event.occurred_at, mock_occurred_at)
            self.assertEqual(event.subnet, mock_subnet)
            self.assertEqual(event.ec2_ami_id, mock_ec2_ami_id)
            self.assertEqual(event.instance_type, mock_instance_type)

    def test_command_output_no_log_content(self):
        """Test that a non-log is not processed."""
        out = StringIO()
        mock_instance_id = str(uuid.uuid4())
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())

        mock_sqs_message_body = {
            'Records': [
                {
                    's3': {
                        'bucket': {
                            'name': 'test-bucket',
                        },
                        'object': {
                            'key': 'path/to/log',
                        },
                    },
                }
            ]
        }
        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = ''

        expected_out = _('No instances or events to save to the DB.')

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3, \
                patch.object(aws, 'delete_message_from_queue') as mock_del:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = mock_cloudtrail_log
            mock_del.return_value = 'Success'

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn(expected_out, actual_stdout)

        instances = list(Instance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(InstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        self.assertListEqual(instances, [])
        self.assertListEqual(instance_events, [])

    def test_command_output_non_on_off_events(self):
        """Test that non on/off events are not processed."""
        out = StringIO()
        mock_instance_id = str(uuid.uuid4())
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())

        mock_sqs_message_body = {
            'Records': [
                {
                    's3': {
                        'bucket': {
                            'name': 'test-bucket',
                        },
                        'object': {
                            'key': 'path/to/log',
                        },
                    },
                }
            ]
        }
        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = mock_cloudtrail_log = {
            'Records': [
                {
                    'eventSource': 'null.amazonaws.com',
                },
                {
                    'errorCode': 123,
                },
                {
                    'eventName': 'InvalidEvent'
                }
            ]
        }

        expected_out = _('No instances or events to save to the DB.')

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3, \
                patch.object(aws, 'delete_message_from_queue') as mock_delete:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = json.dumps(mock_cloudtrail_log)
            mock_delete.return_value = 'Success'

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn(expected_out, actual_stdout)

        instances = list(Instance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(InstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        self.assertListEqual(instances, [])
        self.assertListEqual(instance_events, [])
