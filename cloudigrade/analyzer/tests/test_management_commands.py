"""Collection of tests for Analyzer management commands."""
import datetime
import json
import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils.translation import gettext as _

from account.management.commands.add_account import aws
from util.tests import helper


class AnalyzeLogTest(TestCase):
    """Analyze Log management command test case."""

    def test_command_output_success(self):
        """Test processing a CloudTrail log."""
        out = StringIO()
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_account_id = str(helper.generate_dummy_aws_account_id())
        mock_instance_id = str(uuid.uuid4())
        mock_region = 'us-east-1'
        mock_event_type = 'RunInstances'
        mock_occured_at = datetime.datetime.utcnow().isoformat()
        mock_subnet = 'subnet-9000'
        mock_ec2_ami_id = str(uuid.uuid4())
        mock_instance_type = 't2.nano'

        expected_instances = [(mock_account_id, mock_instance_id, mock_region)]
        expected_instance_events = [
            (mock_instance_id, 'power_on', mock_occured_at, mock_subnet,
             mock_ec2_ami_id, mock_instance_type)
        ]

        expected_out = _('Found instances: {i} and events {e}').format(
            i=expected_instances, e=expected_instance_events)
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
        mock_message = helper.generate_mock_sqs_message(
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
                    'eventTime': mock_occured_at,
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
                        'accountId': mock_account_id
                    }
                }
            ]
        }

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = json.dumps(mock_cloudtrail_log)

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn(expected_out, actual_stdout)

    def test_command_output_no_log_content(self):
        """Test that a non-log is not processed."""
        out = StringIO()
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
        mock_message = helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = ''

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = mock_cloudtrail_log

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn('', actual_stdout)

    def test_command_output_non_on_off_events(self):
        """Test that non on/off events are not processed."""
        out = StringIO()
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
        mock_message = helper.generate_mock_sqs_message(
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

        with patch.object(aws, 'receive_message_from_queue') as mock_receive, \
                patch.object(aws, 'get_object_content_from_s3') as mock_s3:
            mock_receive.return_value = [mock_message]
            mock_s3.return_value = json.dumps(mock_cloudtrail_log)

            call_command('analyze_log', mock_queue_url, stdout=out)

        actual_stdout = out.getvalue()
        self.assertIn('', actual_stdout)
