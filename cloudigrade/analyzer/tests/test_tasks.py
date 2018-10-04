"""Collection of tests for Analyzer tasks."""
import json
import random
from unittest.mock import Mock, call, patch

import faker
from django.conf import settings
from django.test import TestCase

from account.models import (AwsEC2InstanceDefinitions,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage,
                            InstanceEvent)
from account.tests import helper as account_helper
from analyzer import tasks
from analyzer.tests import helper as analyzer_helper
from util.exceptions import EC2InstanceDefinitionNotFound
from util.tests import helper as util_helper

_faker = faker.Faker()


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
        trail_record_1 = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=self.mock_account_id, instance_ids=[
                mock_instance_1.instance_id,
                mock_instance_w.instance_id,
            ], event_time=occurred_at, region=region)
        trail_record_2 = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=self.mock_account_id, instance_ids=[
                mock_instance_2.instance_id,
            ], event_time=occurred_at, region=region)
        trail_record_3 = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=self.mock_account_id, instance_ids=[
                mock_instance_1.instance_id,
                mock_instance_2.instance_id,
                mock_instance_w.instance_id,
                mock_instance_4.instance_id,
            ], event_time=occurred_at, region=region)
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
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_changed_instance_type_existing_instance(
            self, mock_receive, mock_s3, mock_del, mock_session,
            mock_inspection):
        """
        Test that analyze_log correctly handles attribute change messages.

        This test focuses on just getting an instance attribute change message
        for an already known instance. Since we already know the instance,
        we do not need to make an extra describe instance call to AWS.
        """
        instance_type = 't1.potato'
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        gen_instance = account_helper.generate_aws_instance(
            self.mock_account, region='us-east-1')
        trail_record = \
            analyzer_helper.generate_cloudtrail_modify_instances_record(
                aws_account_id=self.mock_account_id,
                instance_id=gen_instance.ec2_instance_id,
                instance_type=instance_type,
                region='us-east-1')
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)
        mock_inspection.assert_not_called()
        mock_del.assert_called_with(settings.CLOUDTRAIL_EVENT_URL,
                                    [sqs_message])

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 1)
        instance = instances[0]
        self.assertEqual(
            instance.ec2_instance_id, gen_instance.ec2_instance_id)
        self.assertEqual(instance.account_id, self.mock_account.id)

        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.instance, instance)
        self.assertEqual(event.instance_type, instance_type)
        self.assertEqual(event.event_type, 'attribute_change')

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_ec2_instance')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_changed_instance_type_new_instance(
            self, mock_receive, mock_s3, mock_del, mock_session, mock_ec2,
            mock_inspection):
        """
        Test that analyze_log correctly handles attribute change messages.

        This test focuses on just getting an instance attribute change message
        for an unknown instance. Here we verify that the two first calls
        correctly re-use the instance_type returned by the single describe,
        and that the attribute change event uses the new instance type.
        """
        instance_type = 't1.potato'
        new_instance_type = 't2.potato'
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        image_1 = account_helper.generate_aws_image()
        mock_instance = util_helper.generate_mock_ec2_instance(
            instance_type=instance_type, image_id=image_1.ec2_ami_id)
        on_record = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[mock_instance.instance_id], region='us-east-1')
        off_record = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[mock_instance.instance_id],
            event_name='StopInstances', region='us-east-1')
        change_type_record = \
            analyzer_helper.generate_cloudtrail_modify_instances_record(
                aws_account_id=self.mock_account_id,
                instance_id=mock_instance.instance_id,
                instance_type=new_instance_type, region='us-east-1')
        s3_content = {'Records': [on_record, off_record, change_type_record]}
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
        mock_del.assert_called_with(settings.CLOUDTRAIL_EVENT_URL,
                                    [sqs_message])

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 1)
        instance = instances[0]
        self.assertEqual(
            instance.ec2_instance_id, mock_instance.instance_id)
        self.assertEqual(instance.account_id, self.mock_account.id)

        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 3)

        on_event = AwsInstanceEvent.objects.filter(
            event_type='power_on').first()
        self.assertEqual(on_event.instance_type, mock_instance.instance_type)

        off_event = AwsInstanceEvent.objects.filter(
            event_type='power_off').first()
        self.assertEqual(off_event.instance_type, mock_instance.instance_type)

        change_event = AwsInstanceEvent.objects.filter(
            event_type='attribute_change').first()
        self.assertEqual(change_event.instance_type, new_instance_type)

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
        trail_record = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=self.mock_account_id,
            instance_ids=[mock_instance.instance_id],
            event_name='TerminateInstances')
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

        This can happen when a user deletes their AWS role, deletes their
        cloudigrade account, and leave their cloudtrail running.

        If this happens, we want to delete the message for the nonexistant
        account from the queue, and log a warning.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_instance = util_helper.generate_mock_ec2_instance_incomplete()
        trail_record = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=util_helper.generate_dummy_aws_account_id(),
            instance_ids=[mock_instance.instance_id])
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 0)
        self.assertEqual(len(failures), 0)
        mock_inspection.assert_not_called()

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 0)
        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 0)
        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 0)

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_with_invalid_cloudtrail_log_content(
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
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = 'hello world'

        successes, failures = tasks.analyze_log()
        self.assertEqual(len(successes), 0)
        self.assertEqual(len(failures), 1)

        mock_del.assert_not_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_with_irrelevant_log_activity(
            self, mock_receive, mock_s3, mock_del):
        """Test that logs without relevant data are effectively ignored."""
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        irrelevant_log = {
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

        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(irrelevant_log)

        tasks.analyze_log()
        mock_del.assert_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_ami_tags_added_success(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags added."""
        ami = account_helper.generate_aws_image()
        self.assertFalse(ami.openshift_detected)

        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        trail_record = analyzer_helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.mock_account_id, image_ids=[ami.ec2_ami_id],
            tag_names=[tasks.aws.OPENSHIFT_TAG], event_name=tasks.CREATE_TAG)
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        updated_ami = AwsMachineImage.objects.get(ec2_ami_id=ami.ec2_ami_id)
        self.assertTrue(updated_ami.openshift_detected)
        mock_del.assert_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_ami_tags_removed_success(
            self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags removed."""
        ami = account_helper.generate_aws_image(openshift_detected=True)
        self.assertTrue(ami.openshift_detected)

        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        trail_record = analyzer_helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.mock_account_id, image_ids=[ami.ec2_ami_id],
            tag_names=[tasks.aws.OPENSHIFT_TAG], event_name=tasks.DELETE_TAG)
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        updated_ami = AwsMachineImage.objects.get(ec2_ami_id=ami.ec2_ami_id)
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
        new_ami_id = util_helper.generate_dummy_image_id()
        image_data = util_helper.generate_dummy_describe_image(
            image_id=new_ami_id,
        )
        mock_describe.return_value = [image_data]

        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        trail_record = analyzer_helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.mock_account_id, image_ids=[new_ami_id],
            tag_names=[tasks.aws.OPENSHIFT_TAG], event_name=tasks.CREATE_TAG,
            region=region)
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        new_ami = AwsMachineImage.objects.get(ec2_ami_id=new_ami_id)
        self.assertTrue(new_ami.openshift_detected)
        mock_del.assert_called()
        mock_inspection.assert_called_once_with(self.mock_arn, new_ami_id,
                                                region)

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_other_tags_ignored(
            self, mock_receive, mock_s3, mock_del):
        """
        Test tag processing where unknown tags should be ignored.

        In this case, the log data includes a new AMI ID. If we cared about the
        referenced tag, this operation would also describe that AMI and add it
        to our model database. However, since the tags in the log are not
        relevant to our interests, we should completely ignore the new AMI.
        """
        new_ami_id = util_helper.generate_dummy_image_id()

        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        trail_record = analyzer_helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.mock_account_id, image_ids=[new_ami_id],
            tag_names=[_faker.slug()], event_name=tasks.CREATE_TAG)
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        all_images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(all_images), 0)
        mock_del.assert_called()

    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_non_ami_resources_with_tags_ignored(
            self, mock_receive, mock_s3, mock_del):
        """Test tag processing where non-AMI resources should be ignored."""
        some_ignored_id = _faker.uuid4()

        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        trail_record = analyzer_helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.mock_account_id, image_ids=[some_ignored_id],
            tag_names=[_faker.slug()], event_name=tasks.CREATE_TAG)
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        all_images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(all_images), 0)
        mock_del.assert_called()

    @patch('analyzer.tasks.repopulate_ec2_instance_mapping.delay')
    @patch('analyzer.tasks.AwsEC2InstanceDefinitions.objects.get')
    def test_get_instance_definition_returns_value_in_db(
            self, mock_lookup, mock_remap):
        """Test that task isn't ran if instance definition already exists."""
        mock_instance_definition = Mock()
        mock_instance_definition.instance_type = 't3.nano'
        mock_instance_definition.memory = '0.5'
        mock_instance_definition.vcpu = '2'
        mock_lookup.return_value = mock_instance_definition

        instance = mock_lookup()
        self.assertEqual(mock_instance_definition, instance)
        mock_remap.assert_not_called()

    @patch('analyzer.tasks.repopulate_ec2_instance_mapping.delay')
    @patch('analyzer.tasks.AwsEC2InstanceDefinitions.objects.get')
    def test_get_instance_definition_triggers_task(
            self, mock_lookup, mock_remap):
        """Test that task isn't ran if instance definition already exists."""
        mock_lookup.side_effect = AwsEC2InstanceDefinitions.DoesNotExist()
        with self.assertRaises(EC2InstanceDefinitionNotFound):
            tasks._get_instance_definition('t3.nano')

        mock_remap.assert_called()

    @patch('analyzer.tasks.AwsEC2InstanceDefinitions.objects.update_or_create')
    @patch('json.load')
    @patch('urllib.request.urlopen')
    def test_repopulate_ec2_instance_mapping(
            self, mock_request, mock_json_load, mock_db_create):
        """Test that repopulate_ec2_instance_mapping creates db objects."""
        mock_json_load.return_value = {
            'products': {
                'S25N2BEFE3CSAAXK': {
                    'sku': 'S25N2BEFE3CSAAXK',
                    'productFamily': 'Compute Instance',
                    'attributes': {
                        'servicecode': 'AmazonEC2',
                        'location': 'EU (Ireland)',
                        'locationType': 'AWS Region',
                        'instanceType': 'r5d.12xlarge',
                        'currentGeneration': 'Yes',
                        'instanceFamily': 'Memory optimized',
                        'vcpu': '48',
                        'physicalProcessor': 'Intel Xeon Platinum 8175',
                        'memory': '384 GiB',
                        'storage': '2 x 900 NVMe SSD',
                        'networkPerformance': '10 Gigabit',
                        'processorArchitecture': '64-bit',
                        'tenancy': 'Shared',
                        'operatingSystem': 'Windows',
                        'licenseModel': 'No License required',
                        'usagetype': 'EU-BoxUsage:r5d.12xlarge',
                        'operation': 'RunInstances:0002',
                        'capacitystatus': 'Used',
                        'ecu': '173',
                        'normalizationSizeFactor': '96',
                        'preInstalledSw': 'NA',
                        'servicename': 'Amazon Elastic Compute Cloud'
                    }
                }
            }
        }
        tasks.repopulate_ec2_instance_mapping()
        mock_db_create.assert_called_with(instance_type='r5d.12xlarge',
                                          memory=384,
                                          vcpu=48)
