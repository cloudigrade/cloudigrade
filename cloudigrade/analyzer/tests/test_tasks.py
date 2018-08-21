"""Collection of tests for Analyzer tasks."""
import datetime
import json
import random
import uuid
from unittest.mock import call, patch

from dateutil import tz
from django.conf import settings
from django.test import TestCase

from account.models import (AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage,
                            InstanceEvent)
from account.tests import helper as account_helper
from analyzer import tasks
from analyzer.tests import helper as analyzer_helper
from util.tests import helper as util_helper


class AnalyzeLogTest(TestCase):
    """Analyze Log management command test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        self.mock_account_id = str(util_helper.generate_dummy_aws_account_id())
        self.mock_arn = util_helper.generate_dummy_arn(self.mock_account_id)
        self.mock_account = account_helper.generate_aws_account(
            arn=self.mock_arn,
            aws_account_id=self.mock_account_id,
            user=self.user)

    def assertExpectedInstance(self, ec2_instance, region):
        """Assert we created an Instance model matching expectations."""
        instance = AwsInstance.objects.get(
            ec2_instance_id=ec2_instance.instance_id)
        self.assertEqual(instance.ec2_instance_id,
                         ec2_instance.instance_id)
        self.assertEqual(instance.account, self.mock_account)
        self.assertEqual(instance.region, region)

    def assertExpectedInstanceEvents(self, ec2_instance, expected_count,
                                     event_type, occurred_at):
        """Assert we created InstanceEvents matching expectations."""
        instanceevents = list(AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance.instance_id))

        self.assertEqual(len(instanceevents), expected_count)
        for instanceevent in instanceevents:
            self.assertEqual(instanceevent.instance.ec2_instance_id,
                             ec2_instance.instance_id)
            self.assertEqual(instanceevent.subnet, ec2_instance.subnet_id)
            self.assertEqual(instanceevent.instance_type,
                             ec2_instance.instance_type)
            self.assertEqual(instanceevent.event_type, event_type)
            self.assertEqual(instanceevent.occurred_at, occurred_at)
            self.assertEqual(instanceevent.machineimage.ec2_ami_id,
                             ec2_instance.image_id)

    def assertExpectedImage(self, ec2_instance, described_image,
                            is_windows=False):
        """Assert we created a MachineImage matching expectations."""
        image = AwsMachineImage.objects.get(ec2_ami_id=ec2_instance.image_id)
        self.assertEqual(image.ec2_ami_id, ec2_instance.image_id)
        self.assertEqual(image.ec2_ami_id, described_image['ImageId'])
        self.assertEqual(image.owner_aws_account_id,
                         described_image['OwnerId'])
        self.assertEqual(image.name,
                         described_image['Name'])
        if is_windows:
            self.assertEqual(image.platform, AwsMachineImage.WINDOWS)
        else:
            self.assertEqual(image.platform, AwsMachineImage.NONE)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_ec2_instance')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_images')
    def test_command_output_success_ec2_attributes_included(
            self, mock_describe, mock_receive, mock_s3, mock_del, mock_session,
            mock_ec2, mock_inspection):
        """
        Test processing a CloudTrail log with some interesting data included.

        This test simulates receiving a CloudTrail log that has three records.
        The first record includes power-on events for two instances. The second
        record includes a power-on event for a windows platform instance. The
        third record includes a power-on event for all three instances plus a
        fourth instance. The first instance's image is already known to us.
        The others are all new.

        All events happen simultaneously. This is unusual and probably will not
        happen in practice, but our code should handle it.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]

        # Put all the activity in the same region for testing.
        region = random.choice(util_helper.SOME_AWS_REGIONS)

        # Generate the known image for the first instance.
        image_1 = account_helper.generate_aws_image()

        # Define the mocked EC2 instances.
        mock_instance_1 = util_helper.generate_mock_ec2_instance(
            image_id=image_1.ec2_ami_id)
        mock_instance_2 = util_helper.generate_mock_ec2_instance()
        mock_instance_w = util_helper.generate_mock_ec2_instance(
            platform='windows')
        mock_instance_4 = util_helper.generate_mock_ec2_instance()

        # Define the three Record entries for the S3 log file.
        occurred_at = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        trail_record_1 = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[
                mock_instance_1.instance_id,
                mock_instance_w.instance_id,
            ],
            region=region,
            event_time=occurred_at,
        )
        trail_record_2 = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[
                mock_instance_2.instance_id,
            ],
            region=region,
            event_time=occurred_at,
        )
        trail_record_3 = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[
                mock_instance_1.instance_id,
                mock_instance_2.instance_id,
                mock_instance_w.instance_id,
                mock_instance_4.instance_id,
            ],
            region=region,
            event_time=occurred_at,
        )
        s3_content = {
            'Records': [trail_record_1, trail_record_2, trail_record_3]
        }
        mock_s3.return_value = json.dumps(s3_content)

        # Define the mocked "get instance" behavior.
        mock_instances = {
            mock_instance_1.instance_id: mock_instance_1,
            mock_instance_2.instance_id: mock_instance_2,
            mock_instance_w.instance_id: mock_instance_w,
            mock_instance_4.instance_id: mock_instance_4,
        }

        def get_ec2_instance_side_effect(session, instance_id):
            return mock_instances[instance_id]
        mock_ec2.side_effect = get_ec2_instance_side_effect

        # Define the mocked "describe images" behavior.
        described_image_2 = util_helper.generate_dummy_describe_image(
            image_id=mock_instance_2.image_id,
        )
        described_image_w = util_helper.generate_dummy_describe_image(
            image_id=mock_instance_w.image_id,
        )
        described_image_4 = util_helper.generate_dummy_describe_image(
            image_id=mock_instance_4.image_id,
        )
        mock_images_data = {
            mock_instance_2.image_id: described_image_2,
            mock_instance_w.image_id: described_image_w,
            mock_instance_4.image_id: described_image_4,
        }

        def describe_images_side_effect(session, image_ids, source_region):
            return [
                mock_images_data[image_id]
                for image_id in image_ids
            ]
        mock_describe.side_effect = describe_images_side_effect

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        mock_del.assert_called()
        mock_inspection.assert_called()
        inspection_calls = mock_inspection.call_args_list
        # Note: We do not start inspection for the image we already knew about
        # or the image for the windows instance. We only start inspection for
        # new not-windows images.
        self.assertEqual(len(inspection_calls), 2)
        instance_2_call = call(self.mock_arn, mock_instance_2.image_id, region)
        instance_4_call = call(self.mock_arn, mock_instance_4.image_id, region)
        self.assertIn(instance_2_call, inspection_calls)
        self.assertIn(instance_4_call, inspection_calls)

        # Check the objects we created around the first instance.
        self.assertExpectedInstance(mock_instance_1, region)
        self.assertExpectedInstanceEvents(
            mock_instance_1, 2, InstanceEvent.TYPE.power_on, occurred_at)
        # Unlike the other cases, we should not have created a new image here.
        image_1_after = AwsMachineImage.objects.get(
            ec2_ami_id=mock_instance_1.image_id)
        self.assertEqual(image_1, image_1_after)

        # Check the objects we created around the second instance.
        self.assertExpectedInstance(mock_instance_2, region)
        self.assertExpectedInstanceEvents(
            mock_instance_2, 2, InstanceEvent.TYPE.power_on, occurred_at)
        self.assertExpectedImage(mock_instance_2, described_image_2)

        # Check the objects we created around the windows instance.
        self.assertExpectedInstance(mock_instance_w, region)
        self.assertExpectedInstanceEvents(
            mock_instance_w, 2, InstanceEvent.TYPE.power_on, occurred_at)
        self.assertExpectedImage(mock_instance_w, described_image_w,
                                 is_windows=True)

        # Check the objects we created around the fourth instance.
        self.assertExpectedInstance(mock_instance_4, region)
        self.assertExpectedInstanceEvents(
            mock_instance_4, 1, InstanceEvent.TYPE.power_on, occurred_at)
        self.assertExpectedImage(mock_instance_4, described_image_4)

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_with_multiple_sqs_messages(
            self, mock_receive, mock_s3, mock_del):
        """
        Test that analyze_log correctly handles multiple SQS messages.

        This test simplifies the content of the individual messages and intends
        to focus specifically on the aspect that handles more than one.

        Specifically, we are testing the handling of three messages. The first
        and third messages are valid and should complete successfully. The
        second (middle) message is malformed and should be left on the queue
        for retry later (in practice).
        """
        sqs_messages = [
            analyzer_helper.generate_mock_cloudtrail_sqs_message(),
            analyzer_helper.generate_mock_cloudtrail_sqs_message(),
            analyzer_helper.generate_mock_cloudtrail_sqs_message()
        ]
        mock_receive.return_value = sqs_messages
        simple_content = {'Records': []}
        mock_s3.side_effect = [
            json.dumps(simple_content),
            'hello world',  # invalid CloudTrail S3 log file content
            json.dumps(simple_content),
        ]

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 2)
        self.assertIn(sqs_messages[0], successes)
        self.assertIn(sqs_messages[2], successes)
        self.assertEqual(len(failures), 1)
        self.assertIn(sqs_messages[1], failures)

        mock_del.assert_called()
        delete_message_calls = mock_del.call_args_list
        # Only the first and third message should be deleted.
        self.assertEqual(len(delete_message_calls), 2)
        delete_1_call = call(settings.CLOUDTRAIL_EVENT_URL, [sqs_messages[0]])
        delete_3_call = call(settings.CLOUDTRAIL_EVENT_URL, [sqs_messages[2]])
        self.assertIn(delete_1_call, delete_message_calls)
        self.assertIn(delete_3_call, delete_message_calls)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_ec2_instance')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_when_instance_was_terminated(
            self, mock_receive, mock_s3, mock_del, mock_session,
            mock_ec2, mock_inspection):
        """
        Test appropriate handling when the AWS instance is not accessible.

        This can happen when we receive an event but the instance has been
        terminated and erased from AWS before we get to request its data.

        Starting with a database that has only a user and its cloud account,
        this test should result in a new instance and one event for it, but
        no images should be created.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_instance = util_helper.generate_mock_ec2_instance_incomplete()
        trail_record = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[mock_instance.instance_id],
            event_name='TerminateInstances',
        )
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)
        mock_instances = {
            mock_instance.instance_id: mock_instance,
        }

        def get_ec2_instance_side_effect(session, instance_id):
            return mock_instances[instance_id]

        mock_ec2.side_effect = get_ec2_instance_side_effect

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)
        mock_inspection.assert_not_called()
        mock_del.assert_called_with(settings.CLOUDTRAIL_EVENT_URL,
                                    [sqs_message])

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 1)
        instance = instances[0]
        self.assertEqual(instance.ec2_instance_id, mock_instance.instance_id)
        self.assertEqual(instance.account_id, self.mock_account.id)

        # Note that the event is stored in a partially known state.
        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.instance, instance)
        self.assertIsNone(event.subnet)
        self.assertIsNone(event.instance_type)
        self.assertIsNone(event.machineimage)

        # Note that no image is stored at all.
        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 0)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_ec2_instance')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_when_account_is_not_known(
            self, mock_receive, mock_s3, mock_del, mock_session,
            mock_ec2, mock_inspection):
        """
        Test appropriate handling when the account ID in the log is unknown.

        It is unclear exactly how this can happen in practice, but if this
        does happen, we should stop processing the file, report an error, and
        leave the corresponding message on the queue to try again later.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_instance = util_helper.generate_mock_ec2_instance_incomplete()
        trail_record = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id=util_helper.generate_dummy_aws_account_id(),
            instance_ids=[mock_instance.instance_id],
        )
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 0)
        self.assertEqual(len(failures), 1)
        mock_inspection.assert_not_called()
        mock_del.assert_not_called()

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 0)
        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 0)
        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 0)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_ec2_instance')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_image')
    def test_command_output_success_lookup_ec2_attributes(
            self, mock_describe, mock_receive, mock_s3, mock_del, mock_session,
            mock_ec2, mock_inspection):
        """Test processing a CloudTrail log with missing instance data."""
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_instance_id = util_helper.generate_dummy_instance_id()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_event_type = 'StartInstances'
        now = datetime.datetime.utcnow()
        # Work around for sqlite handling of microseconds
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )
        mock_subnet = 'subnet-9000'
        mock_ec2_ami_id = util_helper.generate_dummy_image_id()
        mock_instance_type = 't2.nano'

        mock_instance = util_helper.generate_mock_ec2_instance(
            mock_instance_id, mock_ec2_ami_id, mock_subnet, None,
            mock_instance_type
        )
        mock_inspection.delay.return_value = True

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
                },
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
                    },
                    'errorCode': 'potato'
                },
                {
                    'awsRegion': mock_region,
                    'eventName': 'iiam',
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

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)
        mock_del.return_value = 'Success'
        mock_ec2.return_value = mock_instance
        image_data = util_helper.generate_dummy_describe_image(
            image_id=mock_ec2_ami_id,
        )
        mock_describe.return_value = image_data

        tasks.analyze_log()

        instances = list(AwsInstance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(AwsInstanceEvent.objects.filter(
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
            self.assertEqual(event.machineimage.ec2_ami_id, mock_ec2_ami_id)
            self.assertEqual(event.instance_type, mock_instance_type)

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_command_output_no_log_content(
            self, mock_receive, mock_s3, mock_del):
        """
        Test that a malformed (not JSON) log is not processed.

        This is a "supported" failure case. If somehow we cannot process the
        log file, the expected behavior is to log an exception message and not
        delete the SQS message that led us to that message. This means that the
        message would be picked up again and again with each task run. This is
        okay and expected, and we will (eventually) configure a DLQ to take any
        messages that we repeatedly fail to process.
        """
        mock_instance_id = util_helper.generate_dummy_instance_id()
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

        mock_cloudtrail_log = 'hello world'

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = mock_cloudtrail_log

        tasks.analyze_log()

        instances = list(AwsInstance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(AwsInstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        self.assertListEqual(instances, [])
        self.assertListEqual(instance_events, [])

        mock_del.assert_not_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_command_output_non_on_off_events(
            self, mock_receive, mock_s3, mock_del):
        """Test that non on/off events are not processed."""
        mock_instance_id = util_helper.generate_dummy_instance_id()
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
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    }
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

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)
        mock_del.return_value = 'Success'

        tasks.analyze_log()

        instances = list(AwsInstance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(AwsInstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        self.assertListEqual(instances, [])
        self.assertListEqual(instance_events, [])
        mock_del.assert_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_ami_tags_added_success(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags added."""
        ami = account_helper.generate_aws_image()
        ami_id = ami.ec2_ami_id

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

        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)

        now = datetime.datetime.utcnow()
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )

        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = {
            'Records': [
                {
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventSource': 'ec2.amazonaws.com',
                    'awsRegion': mock_region,
                    'eventName': tasks.CREATE_TAG,
                    'requestParameters': {
                        'resourcesSet': {
                            'items': [
                                {
                                    'resourceId': ami_id
                                }
                            ]
                        },
                        'tagSet': {
                            'items': [
                                {
                                    'key': tasks.aws.OPENSHIFT_TAG,
                                    'value': tasks.aws.OPENSHIFT_TAG
                                }
                            ]
                        }
                    },
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    },
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        tasks.analyze_log()

        updated_ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        self.assertTrue(updated_ami.openshift_detected)
        mock_del.assert_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_ami_tags_removed_success(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags removed."""
        ami = account_helper.generate_aws_image(openshift_detected=True)
        ami_id = ami.ec2_ami_id

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

        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)

        now = datetime.datetime.utcnow()
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )

        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = {
            'Records': [
                {
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventSource': 'ec2.amazonaws.com',
                    'awsRegion': mock_region,
                    'eventName': tasks.DELETE_TAG,
                    'requestParameters': {
                        'resourcesSet': {
                            'items': [
                                {
                                    'resourceId': ami_id
                                }
                            ]
                        },
                        'tagSet': {
                            'items': [
                                {
                                    'key': tasks.aws.OPENSHIFT_TAG,
                                    'value': tasks.aws.OPENSHIFT_TAG
                                }
                            ]
                        }
                    },
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    },
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        tasks.analyze_log()

        updated_ami = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        self.assertFalse(updated_ami.openshift_detected)
        mock_del.assert_called()

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_images')
    def test_ami_tags_unknown_ami_is_added(
            self, mock_describe, mock_receive, mock_s3, mock_del,
            mock_session, mock_inspection):
        """
        Test processing a log for ami tags reference a new ami_id.

        In this case, we should attempt to describe the image and save it to
        our image model.
        """
        mock_ec2_ami_id = util_helper.generate_dummy_image_id()

        image_data = util_helper.generate_dummy_describe_image(
            image_id=mock_ec2_ami_id,
        )
        mock_describe.return_value = [image_data]

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

        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)

        now = datetime.datetime.utcnow()
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )

        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = {
            'Records': [
                {
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventSource': 'ec2.amazonaws.com',
                    'awsRegion': mock_region,
                    'eventName': tasks.DELETE_TAG,
                    'requestParameters': {
                        'resourcesSet': {
                            'items': [
                                {
                                    'resourceId': mock_ec2_ami_id
                                }
                            ]
                        },
                        'tagSet': {
                            'items': [
                                {
                                    'key': tasks.aws.OPENSHIFT_TAG,
                                    'value': tasks.aws.OPENSHIFT_TAG
                                }
                            ]
                        }
                    },
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    },
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        try:
            tasks.analyze_log()
        except Exception:
            self.fail('Should not raise exceptions when ami not found')

        mock_inspection.assert_called_once_with(self.mock_arn,
                                                mock_ec2_ami_id,
                                                mock_region)
        mock_del.assert_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_other_tags_ignored(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for other tags ignored."""
        mock_instance_id = util_helper.generate_dummy_instance_id()

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

        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)

        now = datetime.datetime.utcnow()
        mock_occurred_at = datetime.datetime(
            year=now.year, month=now.month, day=now.day, hour=now.hour,
            minute=now.minute, second=now.second, tzinfo=tz.tzutc()
        )

        mock_message = util_helper.generate_mock_sqs_message(
            mock_queue_url,
            json.dumps(mock_sqs_message_body),
            mock_receipt_handle
        )

        mock_cloudtrail_log = {
            'Records': [
                {
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventSource': 'ec2.amazonaws.com',
                    'awsRegion': mock_region,
                    'eventName': tasks.DELETE_TAG,
                    'requestParameters': {
                        'resourcesSet': {
                            'items': [
                                {
                                    'resourceId': mock_instance_id
                                }
                            ]
                        },
                        'tagSet': {
                            'items': [
                                {
                                    'key': tasks.aws.OPENSHIFT_TAG,
                                    'value': tasks.aws.OPENSHIFT_TAG
                                }
                            ]
                        }
                    },
                    'userIdentity': {
                        'accountId': self.mock_account_id
                    },
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        try:
            tasks.analyze_log()
        except Exception:
            self.fail('Should not raise exceptions for ignored tag events.')
        mock_del.assert_called()
