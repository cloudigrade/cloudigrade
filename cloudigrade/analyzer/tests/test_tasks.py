"""Collection of tests for Analyzer management commands."""
import datetime
import json
import random
import uuid
from unittest.mock import patch

from dateutil import tz
from django.test import TestCase

from account.models import (AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage,
                            ImageTag,
                            InstanceEvent)
from account.tests import helper as account_helper
from analyzer import tasks
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
    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
    def test_command_output_success_ec2_attributes_included(
            self, mock_receive, mock_s3, mock_del, mock_session, mock_ec2,
            mock_inspection):
        """Test processing a CloudTrail log with all data included."""
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
        mock_session.return_value = 'Session'
        mock_ec2.return_value = mock_instance

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

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_ec2_instance')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
    def test_command_output_success_lookup_ec2_attributes(
            self, mock_receive, mock_s3, mock_del, mock_session, mock_ec2,
            mock_inspection):
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
        mock_session.return_value = 'Session'
        mock_ec2.return_value = mock_instance

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

    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
    def test_command_output_no_log_content(
            self, mock_receive, mock_s3, mock_del):
        """Test that a non-log is not processed."""
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

        mock_cloudtrail_log = ''

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = mock_cloudtrail_log
        mock_del.return_value = 'Success'

        tasks.analyze_log()

        instances = list(AwsInstance.objects.filter(
            ec2_instance_id=mock_instance_id).all())
        instance_events = list(AwsInstanceEvent.objects.filter(
            instance=instances[0]).all()) if instances else []

        self.assertListEqual(instances, [])
        self.assertListEqual(instance_events, [])

    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
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

    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
    def test_ami_tags_added_success(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags added."""
        mock_user = util_helper.generate_test_user()
        mock_arn = util_helper.generate_dummy_arn()
        aws_account = AwsAccount(
            user=mock_user,
            name='test',
            aws_account_id='1234',
            account_arn=mock_arn)
        aws_account.save()

        mock_ec2_ami_id = util_helper.generate_dummy_image_id()
        aws_machine_image = AwsMachineImage(
            account=aws_account, ec2_ami_id=mock_ec2_ami_id)
        aws_machine_image.save()

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
                                    'resourceId': mock_ec2_ami_id
                                }
                            ]
                        },
                        'tagSet': {
                            'items': [
                                {
                                    'key': tasks.AWS_OPENSHIFT_TAG,
                                    'value': tasks.AWS_OPENSHIFT_TAG
                                }
                            ]
                        }
                    }
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        tasks.analyze_log()

        self.assertNotEqual(None, aws_machine_image.tags.filter(
            description=tasks.OPENSHIFT_MODEL_TAG).first())

    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
    def test_ami_tags_removed_success(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags removed."""
        mock_user = util_helper.generate_test_user()
        mock_arn = util_helper.generate_dummy_arn()
        aws_account = AwsAccount(
            user=mock_user,
            name='test',
            aws_account_id='1234',
            account_arn=mock_arn)
        aws_account.save()

        mock_ec2_ami_id = util_helper.generate_dummy_image_id()
        aws_machine_image = AwsMachineImage(
            account=aws_account, ec2_ami_id=mock_ec2_ami_id)
        aws_machine_image.save()

        openshift_tag = ImageTag.objects.filter(
            description=tasks.OPENSHIFT_MODEL_TAG).first()
        aws_machine_image.tags.add(openshift_tag)

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
                                    'key': tasks.AWS_OPENSHIFT_TAG,
                                    'value': tasks.AWS_OPENSHIFT_TAG
                                }
                            ]
                        }
                    }
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        tasks.analyze_log()

        self.assertEqual(None, aws_machine_image.tags.filter(
            description=tasks.OPENSHIFT_MODEL_TAG).first())

    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
    def test_ami_tags_missing_failure(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a log for ami tags reference bad ami_id."""
        mock_ec2_ami_id = util_helper.generate_dummy_image_id()

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
                                    'key': tasks.AWS_OPENSHIFT_TAG,
                                    'value': tasks.AWS_OPENSHIFT_TAG
                                }
                            ]
                        }
                    }
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        try:
            tasks.analyze_log()
        except Exception:
            self.fail('Should not raise exceptions when ami not found')

    @patch('analyzer.tasks.aws.delete_message_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.receive_message_from_queue')
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
                                    'key': tasks.AWS_OPENSHIFT_TAG,
                                    'value': tasks.AWS_OPENSHIFT_TAG
                                }
                            ]
                        }
                    }
                }
            ]
        }

        mock_receive.return_value = [mock_message]
        mock_s3.return_value = json.dumps(mock_cloudtrail_log)

        try:
            tasks.analyze_log()
        except Exception:
            self.fail('Should not raise exceptions for ignored tag events.')
