"""Collection of tests for Analyzer tasks."""
import json
import random
from unittest.mock import Mock, call, patch

import faker
from django.conf import settings
from django.test import TestCase

from account.models import (
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    InstanceEvent,
    Run
)
from account.tests import helper as account_helper
from analyzer import cloudtrail, tasks
from analyzer.tests import helper as analyzer_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class AnalyzeLogTest(TestCase):
    """Analyze Log management command test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = account_helper.generate_aws_account(
            aws_account_id=self.aws_account_id,
            user=self.user,
            created_at=util_helper.utc_dt(2017, 12, 1, 0, 0, 0),
        )
        account_helper.generate_aws_ec2_definitions()

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_instances')
    @patch('analyzer.tasks.aws.describe_images')
    def test_analyze_log_same_instance_various_things(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
    ):
        """
        Analyze CloudTrail records for one instance doing various things.

        This test covers multiple "interesting" use cases including:

        - starting a new instance for the first time
        - that instance uses an image we've not yet seen
        - rebooting that instance
        - stopping that instance
        - changing the instance's type
        - stopping the instance

        We verify that we DO NOT describe_instances because the CloudTrail
        message for running a new instance should have enough data to define
        our model. We verify that we DO describe_images for the new image. We
        verify that the appropriate events and runs are created and that the
        instance type change correctly affects its following event and run.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = random.choice(util_helper.SOME_AWS_REGIONS)

        # Starting instance type and then the one it changes to.
        instance_type = util_helper.get_random_instance_type()
        new_instance_type = util_helper.get_random_instance_type(
            avoid=instance_type
        )

        ec2_instance_id = util_helper.generate_dummy_instance_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()

        # Define the mocked "describe images" behavior.
        described_image = util_helper.generate_dummy_describe_image(ec2_ami_id)
        described_images = {ec2_ami_id: described_image}

        def describe_images_side_effect(__, image_ids, ___):
            return [described_images[image_id] for image_id in image_ids]
        mock_describe_images.side_effect = describe_images_side_effect

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        occurred_at_reboot = util_helper.utc_dt(2018, 1, 2, 0, 0, 0)
        occurred_at_stop = util_helper.utc_dt(2018, 1, 3, 0, 0, 0)
        occurred_at_modify = util_helper.utc_dt(2018, 1, 4, 0, 0, 0)
        occurred_at_start = util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        s3_content = {
            'Records': [
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='RunInstances',
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                ),
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='RebootInstances',
                    event_time=occurred_at_reboot,
                    region=region,
                    # instance_type=instance_type,  # not relevant for reboot
                    # image_id=ec2_ami_id,  # not relevant for reboot
                ),
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='StopInstances',
                    event_time=occurred_at_stop,
                    region=region,
                    # instance_type=instance_type,  # not relevant for stop
                    # image_id=ec2_ami_id,  # not relevant for stop
                ),
                analyzer_helper.generate_cloudtrail_modify_instance_record(
                    aws_account_id=self.aws_account_id,
                    instance_id=ec2_instance_id,
                    instance_type=new_instance_type,
                    event_time=occurred_at_modify,
                    region=region,
                ),
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='StartInstances',
                    event_time=occurred_at_start,
                    region=region,
                    # instance_type=instance_type,  # not relevant for start
                    # image_id=ec2_ami_id,  # not relevant for start
                ),
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(
            settings.CLOUDTRAIL_EVENT_URL, [sqs_message]
        )

        # We should *not* have described the instance because the CloudTrail
        # messages should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We *should* have described the image because it is new to us.
        mock_describe_images.assert_called()

        # Inspection *should* have started for this new image.
        mock_inspection.assert_called()
        inspection_calls = mock_inspection.call_args_list
        self.assertEqual(len(inspection_calls), 1)
        instance_call = call(self.account.account_arn, ec2_ami_id, region)
        self.assertIn(instance_call, inspection_calls)

        # Assert that the correct instance was saved.
        instance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.account, self.account)
        self.assertEqual(instance.region, region)

        # Assert that the correct instance events were saved.
        # We expect to find *four* events. Note that "reboot" does not cause us
        # to generate a new event because we know it's already running.
        instanceevents = list(AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance_id
        ).order_by('occurred_at'))
        self.assertEqual(len(instanceevents), 4)

        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[1].occurred_at, occurred_at_stop)
        self.assertEqual(instanceevents[2].occurred_at, occurred_at_modify)
        self.assertEqual(instanceevents[3].occurred_at, occurred_at_start)

        self.assertEqual(instanceevents[0].event_type, 'power_on')
        self.assertEqual(instanceevents[1].event_type, 'power_off')
        self.assertEqual(instanceevents[2].event_type, 'attribute_change')
        self.assertEqual(instanceevents[3].event_type, 'power_on')

        self.assertEqual(instanceevents[0].instance_type, instance_type)
        self.assertEqual(instanceevents[1].instance_type, None)
        self.assertEqual(instanceevents[2].instance_type, new_instance_type)
        self.assertEqual(instanceevents[3].instance_type, None)

        # Assert that as a side-effect two runs were created.
        runs = Run.objects.filter(instance=instance).order_by('start_time')
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertEqual(runs[0].end_time, occurred_at_stop)
        self.assertEqual(runs[1].instance_type, new_instance_type)
        self.assertEqual(runs[1].start_time, occurred_at_start)
        self.assertIsNone(runs[1].end_time)

        # Assert that the correct image was saved.
        image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
        self.assertEqual(image.region, region)
        self.assertEqual(
            image.owner_aws_account_id, described_image['OwnerId']
        )
        self.assertEqual(image.status, image.PENDING)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_instances')
    @patch('analyzer.tasks.aws.describe_images')
    def test_analyze_log_run_instance_windows_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
    ):
        """
        Analyze CloudTrail records for a Windows instance.

        Windows treatment is special because when we describe the image and
        discover that it has the "Windows" platform set, we save our model in
        an already-inspected state.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instance_type = util_helper.get_random_instance_type()

        ec2_instance_id = util_helper.generate_dummy_instance_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()

        # Define the mocked "describe images" behavior.
        described_image = util_helper.generate_dummy_describe_image(
            ec2_ami_id, platform='Windows'
        )
        described_images = {ec2_ami_id: described_image}

        def describe_images_side_effect(__, image_ids, ___):
            return [described_images[image_id] for image_id in image_ids]
        mock_describe_images.side_effect = describe_images_side_effect

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            'Records': [
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='RunInstances',
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                ),
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(
            settings.CLOUDTRAIL_EVENT_URL, [sqs_message]
        )

        # We should *not* have described the instance because the CloudTrail
        # messages should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We *should* have described the image because it is new to us.
        mock_describe_images.assert_called()

        # Inspection should *not* have started for this new image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        instance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.account, self.account)
        self.assertEqual(instance.region, region)

        # Assert that the correct instance event was saved.
        instanceevents = list(AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance_id
        ).order_by('occurred_at'))
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[0].event_type, 'power_on')
        self.assertEqual(instanceevents[0].instance_type, instance_type)

        # Assert that as a side-effect one run was created.
        runs = Run.objects.filter(instance=instance).order_by('start_time')
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertIsNone(runs[0].end_time)

        # Assert that the correct image was saved.
        image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
        self.assertEqual(image.region, region)
        self.assertEqual(
            image.owner_aws_account_id, described_image['OwnerId']
        )
        self.assertEqual(image.status, image.INSPECTED)
        self.assertEqual(image.platform, image.WINDOWS)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_instances')
    @patch('analyzer.tasks.aws.describe_images')
    def test_analyze_log_run_instance_known_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
    ):
        """
        Analyze CloudTrail records for a new instance with an image we know.

        In this case, we do *no* API describes and just process the CloudTrail
        record to save our model changes.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = random.choice(util_helper.SOME_AWS_REGIONS)
        instance_type = util_helper.get_random_instance_type()

        ec2_instance_id = util_helper.generate_dummy_instance_id()
        known_image = account_helper.generate_aws_image()
        ec2_ami_id = known_image.ec2_ami_id

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            'Records': [
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='RunInstances',
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                ),
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(
            settings.CLOUDTRAIL_EVENT_URL, [sqs_message]
        )

        # We should *not* have described the instance because the CloudTrail
        # messages should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We should *not* have described the image because we already know it.
        mock_describe_images.assert_not_called()

        # Inspection should *not* have started for this existing image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        instance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.account, self.account)
        self.assertEqual(instance.region, region)

        # Assert that the correct instance event was saved.
        instanceevents = list(AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance_id
        ).order_by('occurred_at'))
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[0].event_type, 'power_on')
        self.assertEqual(instanceevents[0].instance_type, instance_type)

        # Assert that as a side-effect one run was created.
        runs = Run.objects.filter(instance=instance).order_by('start_time')
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertIsNone(runs[0].end_time)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_instances')
    @patch('analyzer.tasks.aws.describe_images')
    def test_analyze_log_start_old_instance_known_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
    ):
        """
        Analyze CloudTrail records to start an instance with a known image.

        If an account had stopped a instance when it registered with us, we
        never see the "RunInstances" record for that instance. If it starts
        later with a "StartInstances" record, we don't receive enough
        information from the record alone and need to immediately describe the
        instance in AWS in order to populate our model.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = random.choice(util_helper.SOME_AWS_REGIONS)

        image = account_helper.generate_aws_image()
        ec2_ami_id = image.ec2_ami_id

        # Define the mocked "describe instances" behavior.
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        described_instance = util_helper.generate_dummy_describe_instance(
            instance_id=ec2_instance_id, image_id=ec2_ami_id
        )
        instance_type = described_instance['InstanceType']
        described_instances = {ec2_instance_id: described_instance}

        def describe_instances_side_effect(__, instance_ids, ___):
            return dict([
                (instance_id, described_instances[instance_id])
                for instance_id in instance_ids
            ])
        mock_describe_instances.side_effect = describe_instances_side_effect

        # Define the S3 message payload.
        occurred_at_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            'Records': [
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='StartInstances',
                    event_time=occurred_at_start,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                ),
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(
            settings.CLOUDTRAIL_EVENT_URL, [sqs_message]
        )

        # We *should* have described the instance because the CloudTrail record
        # should *not* have enough information to proceed.
        mock_describe_instances.assert_called()

        # We should *not* have described the image because we already know it.
        mock_describe_images.assert_not_called()

        # Inspection should *not* have started for this existing image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        instance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.account, self.account)
        self.assertEqual(instance.region, region)

        # Assert that the correct instance event was saved.
        instanceevents = list(AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance_id
        ).order_by('occurred_at'))
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_start)
        self.assertEqual(instanceevents[0].event_type, 'power_on')
        self.assertEqual(instanceevents[0].instance_type, instance_type)

        # Assert that as a side-effect one run was created.
        runs = Run.objects.filter(instance=instance).order_by('start_time')
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_start)
        self.assertIsNone(runs[0].end_time)

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    @patch('analyzer.tasks.aws.describe_instances')
    @patch('analyzer.tasks.aws.describe_images')
    def test_analyze_log_run_instance_unavailable_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
    ):
        """
        Analyze CloudTrail records for an instance with an unavailable image.

        This could happen if a user has deleted or revoked access to the AMI
        after starting the instance but before we could discover and process
        it. In that case, we save an image with status 'Unavailable' to
        indicate that we can't (and probably never will) inspect it.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = random.choice(util_helper.SOME_AWS_REGIONS)

        instance_type = util_helper.get_random_instance_type()
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()

        # Define the mocked "describe images" behavior.
        mock_describe_images.return_value = []

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            'Records': [
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name='RunInstances',
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                ),
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(
            settings.CLOUDTRAIL_EVENT_URL, [sqs_message]
        )

        # We should *not* have described the instance because the CloudTrail
        # record should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We *should* have described the image because it is new to us.
        mock_describe_images.assert_called()

        # Inspection should *not* have started for this unavailable image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        instance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.account, self.account)
        self.assertEqual(instance.region, region)

        # Assert that the correct instance events were saved.
        # We expect to find *four* events. Note that "reboot" does not cause us
        # to generate a new event because we know it's already running.
        instanceevents = list(AwsInstanceEvent.objects.filter(
            instance__awsinstance__ec2_instance_id=ec2_instance_id
        ).order_by('occurred_at'))
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[0].event_type, 'power_on')
        self.assertEqual(instanceevents[0].instance_type, instance_type)

        # Assert that as a side-effect two runs were created.
        runs = Run.objects.filter(instance=instance).order_by('start_time')
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertEqual(runs[0].end_time, None)

        # Assert that the correct image was saved.
        image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
        self.assertEqual(image.owner_aws_account_id, None)
        self.assertEqual(image.status, image.UNAVAILABLE)

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
            self.account, region='us-east-1')
        trail_record = \
            analyzer_helper.generate_cloudtrail_modify_instance_record(
                aws_account_id=self.aws_account_id,
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
        self.assertEqual(instance.account_id, self.account.id)

        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.instance, instance)
        self.assertEqual(event.instance_type, instance_type)
        self.assertEqual(event.event_type, 'attribute_change')

    @patch('analyzer.tasks.start_image_inspection')
    @patch('analyzer.tasks.aws.describe_instances')
    @patch('analyzer.tasks.aws.get_session')
    @patch('analyzer.tasks.aws.delete_messages_from_queue')
    @patch('analyzer.tasks.aws.get_object_content_from_s3')
    @patch('analyzer.tasks.aws.yield_messages_from_queue')
    def test_analyze_log_when_instance_was_terminated(
        self,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_describe_instances,
        mock_inspection,
    ):
        """
        Test appropriate handling when the AWS instance is not accessible.

        This can happen when we receive an event but the instance has been
        terminated and erased from AWS before we get to request its data.

        Starting with a database that has only a user and its cloud account,
        this test should result in a new instance and one event for it, but
        no images should be created.
        """
        sqs_message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        described_instance = util_helper.generate_dummy_describe_instance()
        s3_content = {
            'Records': [
                analyzer_helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[described_instance['InstanceId']],
                    event_name='TerminateInstances',
                )
            ]
        }
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        # Returning an empty dict matches the behavior seen by manually
        # checking with boto to describe an instance that has been terminated
        # for several hours and is no longer visible to the user.
        mock_describe_instances.return_value = dict()

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
            instance.ec2_instance_id, described_instance['InstanceId']
        )
        self.assertEqual(instance.account_id, self.account.id)

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
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        trail_record = analyzer_helper.generate_cloudtrail_instances_record(
            aws_account_id=util_helper.generate_dummy_aws_account_id(),
            instance_ids=[ec2_instance_id])
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
            aws_account_id=self.aws_account_id,
            image_ids=[ami.ec2_ami_id],
            tag_names=[tasks.aws.OPENSHIFT_TAG],
            event_name=cloudtrail.CREATE_TAG,
        )
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
            aws_account_id=self.aws_account_id,
            image_ids=[ami.ec2_ami_id],
            tag_names=[tasks.aws.OPENSHIFT_TAG],
            event_name=cloudtrail.DELETE_TAG,
        )
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
            aws_account_id=self.aws_account_id,
            image_ids=[new_ami_id],
            tag_names=[tasks.aws.OPENSHIFT_TAG],
            event_name=cloudtrail.CREATE_TAG,
            region=region,
        )
        s3_content = {'Records': [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        new_ami = AwsMachineImage.objects.get(ec2_ami_id=new_ami_id)
        self.assertTrue(new_ami.openshift_detected)
        mock_del.assert_called()
        mock_inspection.assert_called_once_with(
            self.account.account_arn, new_ami_id, region
        )

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
            aws_account_id=self.aws_account_id,
            image_ids=[new_ami_id],
            tag_names=[_faker.slug()],
            event_name=cloudtrail.CREATE_TAG,
        )
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
            aws_account_id=self.aws_account_id,
            image_ids=[some_ignored_id],
            tag_names=[_faker.slug()],
            event_name=cloudtrail.CREATE_TAG,
        )
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

    @patch('analyzer.tasks.AwsEC2InstanceDefinitions.objects.update_or_create')
    @patch('analyzer.tasks.boto3.client')
    def test_repopulate_ec2_instance_mapping(
            self, mock_boto3, mock_db_create):
        """Test that repopulate_ec2_instance_mapping creates db objects."""
        paginator = mock_boto3.return_value.get_paginator.return_value
        paginator.paginate.return_value = [{
            'PriceList': [
                """{
                    "product": {
                        "productFamily": "Compute Instance",
                        "attributes": {
                            "memory": "16 GiB",
                            "vcpu": "2",
                            "capacitystatus": "Used",
                            "instanceType": "r5.large",
                            "tenancy": "Host",
                            "usagetype": "APN1-HostBoxUsage:r5.large",
                            "locationType": "AWS Region",
                            "storage": "EBS only",
                            "normalizationSizeFactor": "4",
                            "instanceFamily": "Memory optimized",
                            "operatingSystem": "RHEL",
                            "servicecode": "AmazonEC2",
                            "physicalProcessor": "Intel Xeon Platinum 8175",
                            "licenseModel": "No License required",
                            "ecu": "10",
                            "currentGeneration": "Yes",
                            "preInstalledSw": "NA",
                            "networkPerformance": "10 Gigabit",
                            "location": "Asia Pacific (Tokyo)",
                            "servicename": "Amazon Elastic Compute Cloud",
                            "processorArchitecture": "64-bit",
                            "operation": "RunInstances:0010"
                        },
                        "sku": "22WY57989R2PA7RB"
                    },
                    "serviceCode": "AmazonEC2",
                    "terms": {
                        "OnDemand": {
                            "22WY57989R2PA7RB.JRTCKXETXF": {
                                "priceDimensions": {
                                    "22WY57989R2PA7RB.JRTCKXETXF.6YS6EN2CT7": {
                                        "unit": "Hrs",
                                        "endRange": "Inf",
                                        "appliesTo": [
                                        ],
                                        "beginRange": "0",
                                        "pricePerUnit": {
                                            "USD": "0.0000000000"
                                        }
                                    }
                                },
                                "sku": "22WY57989R2PA7RB",
                                "effectiveDate": "2018-11-01T00:00:00Z",
                                "offerTermCode": "JRTCKXETXF",
                                "termAttributes": {

                                }
                            }
                        }
                    },
                    "version": "20181122020351",
                    "publicationDate": "2018-11-22T02:03:51Z"
                }"""
            ]
        }]
        tasks.repopulate_ec2_instance_mapping()
        mock_db_create.assert_called_with(instance_type='r5.large',
                                          memory=16,
                                          vcpu=2)

    def test_build_events_info_for_saving(self):
        """Test _build_events_info_for_saving with typical inputs."""
        instance = account_helper.generate_aws_instance(self.account)

        # Note: this time is *after* self.account.created_at.
        occurred_at = '2018-01-02T12:34:56+00:00'

        instance_event = account_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=None
        )
        events_info = tasks._build_events_info_for_saving(self.account,
                                                          instance,
                                                          [instance_event])
        self.assertEqual(len(events_info), 1)

    def test_build_events_info_for_saving_too_old_events(self):
        """Test _build_events_info_for_saving with events that are too old."""
        instance = account_helper.generate_aws_instance(self.account)

        # Note: this time is *before* self.account.created_at.
        occurred_at = '2016-01-02T12:34:56+00:00'

        instance_event = account_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=None
        )
        events_info = tasks._build_events_info_for_saving(self.account,
                                                          instance,
                                                          [instance_event])
        self.assertEqual(len(events_info), 0)

    def test_process_instance_event_recalculate_runs(self):
        """
        Test that we recalculate runs when new instance events occur.

        Initial Runs (2,-):
            [ #------------]

        New power off event at (,13) results in the run being updated (2,13):
            [ ############ ]

        """
        instance = account_helper.generate_aws_instance(self.account)

        started_at = util_helper.utc_dt(2018, 1, 2, 0, 0, 0)

        start_event = account_helper.generate_single_aws_instance_event(
            instance,
            occurred_at=started_at,
            event_type=InstanceEvent.TYPE.power_on,
            no_instance_type=True
        )
        tasks.process_instance_event(start_event)

        occurred_at = util_helper.utc_dt(2018, 1, 13, 0, 0, 0)

        instance_event = account_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_off,
            no_instance_type=True
        )
        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(started_at, runs[0].start_time)
        self.assertEqual(occurred_at, runs[0].end_time)

    @patch('analyzer.tasks.recalculate_runs')
    def test_process_instance_event_new_run(self, mock_recalculate_runs):
        """
        Test new run is created if it occurred after all runs and is power on.

        account.util.recalculate_runs should not be ran in this case.

        Initial Runs (2,5):
            [ ####          ]

        New power on event at (10,) results in 2 runs (2,5) (10,-):
            [ ####    #-----]

        """
        instance = account_helper.generate_aws_instance(self.account)

        run_time = (
            util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
            util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        )

        account_helper.generate_single_run(instance, run_time)

        occurred_at = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
        instance_event = account_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=None
        )
        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(2, len(runs))

        # Since we're adding a new run, recalculate_runs shouldn't be called
        mock_recalculate_runs.assert_not_called()

    def test_process_instance_event_duplicate_start(self):
        """
        Test that recalculate works when a duplicate start event is introduced.

        Initial Runs (5,7):
            [    ###        ]

        New power on event at (1,) results in the run being updated:
            [#######        ]

        New power on event at (3,) results in the run not being updated:
            [#######        ]

        """
        instance_type = 't1.potato'

        instance = account_helper.generate_aws_instance(self.account)

        run_time = [(
            util_helper.utc_dt(2018, 1, 5, 0, 0, 0),
            util_helper.utc_dt(2018, 1, 7, 0, 0, 0)
        )]

        instance_events = account_helper.generate_aws_instance_events(
            instance, run_time,
            instance_type=instance_type
        )
        account_helper.recalculate_runs_from_events(instance_events)

        first_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)

        instance_event = account_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=first_start,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=instance_type
        )

        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(run_time[0][1], runs[0].end_time)
        self.assertEqual(first_start, runs[0].start_time)

        second_start = util_helper.utc_dt(2018, 1, 3, 0, 0, 0)

        dup_start_instance_event = \
            account_helper.generate_single_aws_instance_event(
                instance=instance,
                occurred_at=second_start,
                event_type=InstanceEvent.TYPE.power_on,
                instance_type=instance_type,
            )

        tasks.process_instance_event(dup_start_instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(run_time[0][1], runs[0].end_time)
        self.assertEqual(first_start, runs[0].start_time)

    @patch('analyzer.tasks.recalculate_runs')
    def test_process_instance_event_power_off(self, mock_recalculate_runs):
        """
        Test new run is not if a power off event occurs after all runs.

        account.util.recalculate_runs should not be ran in this case.

        Initial Runs (2,5):
            [ ####          ]

        New power off event at (10,) results in 1 runs (2,5):
            [ ####          ]

        """
        instance = account_helper.generate_aws_instance(self.account)

        run_time = (
            util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
            util_helper.utc_dt(2018, 1, 5, 0, 0, 0)
        )

        account_helper.generate_single_run(instance, run_time)

        occurred_at = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)

        instance_event = account_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_off,
            instance_type=None
        )
        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))

        mock_recalculate_runs.assert_not_called()
