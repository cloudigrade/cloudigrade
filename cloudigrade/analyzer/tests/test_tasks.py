"""Collection of tests for Analyzer management commands."""
import datetime
import json
import random
import uuid
from unittest.mock import patch

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
        Test processing a CloudTrail log with all data included.

        This test simulates receiving a CloudTrail log that has three records.
        The first two records include power-on events for the same instance.
        The third record includes a power-on event for a different instance.
        Both instances are windows. All events reference the same AMI ID.
        """
        mock_queue_url = 'https://sqs.queue.url'
        mock_receipt_handle = str(uuid.uuid4())
        mock_instance_id = util_helper.generate_dummy_instance_id()
        mock_instance_id2 = util_helper.generate_dummy_instance_id()
        mock_region = random.choice(util_helper.SOME_AWS_REGIONS)
        mock_event_type = 'RunInstances'
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
            mock_instance_type, 'windows'
        )
        mock_instance2 = util_helper.generate_mock_ec2_instance(
            mock_instance_id2, mock_ec2_ami_id, mock_subnet, None,
            mock_instance_type, 'windows'
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
                },
                {
                    'awsRegion': mock_region,
                    'eventName': mock_event_type,
                    'eventSource': 'ec2.amazonaws.com',
                    'eventTime': mock_occurred_at.strftime(
                        '%Y-%m-%dT%H:%M:%SZ'
                    ),
                    'eventType': 'DifferentAwsApiCall',
                    'responseElements': {
                        'instancesSet': {
                            'items': [
                                {
                                    'imageId': mock_ec2_ami_id,
                                    'instanceId': mock_instance_id2,
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

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)
        mock_del.return_value = 'Success'
        mock_instances = {
            mock_instance_id: mock_instance,
            mock_instance_id2: mock_instance2,
        }

        def get_ec2_instance_side_effect(session, instance_id):
            return mock_instances[instance_id]

        mock_ec2.side_effect = get_ec2_instance_side_effect
        image_data = util_helper.generate_dummy_describe_image(
            image_id=mock_ec2_ami_id,
        )
        mock_describe.return_value = [image_data]

        tasks.analyze_log()

        instance = AwsInstance.objects.get(ec2_instance_id=mock_instance_id)
        instance_events = list(AwsInstanceEvent.objects.filter(
            instance=instance))
        instance2 = AwsInstance.objects.get(ec2_instance_id=mock_instance_id2)
        instance2_events = list(AwsInstanceEvent.objects.filter(
            instance=instance2))

        self.assertEqual(instance.account, self.mock_account)
        self.assertEqual(instance.ec2_instance_id, mock_instance_id)
        self.assertEqual(instance.region, mock_region)

        self.assertEqual(len(instance_events), 2)
        self.assertEqual(len(instance2_events), 1)
        for event in instance_events:
            self.assertEqual(event.instance, instance)
            self.assertEqual(event.event_type, InstanceEvent.TYPE.power_on)
            self.assertEqual(event.occurred_at, mock_occurred_at)
            self.assertEqual(event.subnet, mock_subnet)
            self.assertEqual(event.machineimage.ec2_ami_id, mock_ec2_ami_id)
            self.assertEqual(event.instance_type, mock_instance_type)

        mock_del.assert_called()

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
