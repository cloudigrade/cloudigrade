"""Collection of tests for aws.tasks.cloudtrail.analyze_log."""
import json
from datetime import timedelta
from unittest.mock import MagicMock, Mock, call, patch

import faker
from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api.clouds.aws import cloudtrail, tasks
from api.clouds.aws.models import AwsInstance, AwsInstanceEvent, AwsMachineImage
from api.models import (
    Instance,
    InstanceEvent,
    MachineImage,
    Run,
)
from api.tests import helper as helper
from util import aws
from util.misc import get_now
from util.tests import helper as util_helper

_faker = faker.Faker()


class AnalyzeLogTest(TestCase):
    """Celery task 'analyze_log' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = helper.generate_cloud_account(
            aws_account_id=self.aws_account_id,
            user=self.user,
            created_at=util_helper.utc_dt(2017, 12, 1, 0, 0, 0),
        )
        helper.generate_instance_type_definitions()

    @util_helper.clouditardis(util_helper.utc_dt(2018, 1, 5, 0, 0, 0))
    @patch("api.util.schedule_concurrent_calculation_task")
    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_instances")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_images")
    def test_analyze_log_same_instance_various_things(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
        mock_schedule_concurrent_calculation_task,
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
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = util_helper.get_random_region()

        # Starting instance type and then the one it changes to.
        instance_type = util_helper.get_random_instance_type()
        new_instance_type = util_helper.get_random_instance_type(avoid=instance_type)

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
            "Records": [
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="RunInstances",
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                ),
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="RebootInstances",
                    event_time=occurred_at_reboot,
                    region=region,
                    # instance_type=instance_type,  # not relevant for reboot
                    # image_id=ec2_ami_id,  # not relevant for reboot
                ),
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="StopInstances",
                    event_time=occurred_at_stop,
                    region=region,
                    # instance_type=instance_type,  # not relevant for stop
                    # image_id=ec2_ami_id,  # not relevant for stop
                ),
                helper.generate_cloudtrail_modify_instance_record(
                    aws_account_id=self.aws_account_id,
                    instance_id=ec2_instance_id,
                    instance_type=new_instance_type,
                    event_time=occurred_at_modify,
                    region=region,
                ),
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="StartInstances",
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
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        # We should *not* have described the instance because the CloudTrail
        # messages should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We *should* have described the image because it is new to us.
        mock_describe_images.assert_called()

        # Inspection *should* have started for this new image.
        mock_inspection.assert_called()
        inspection_calls = mock_inspection.call_args_list
        self.assertEqual(len(inspection_calls), 1)
        instance_call = call(
            self.account.content_object.account_arn, ec2_ami_id, region
        )
        self.assertIn(instance_call, inspection_calls)

        # Assert that the correct instance was saved.
        aws_instance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        instance = aws_instance.instance.get()
        self.assertEqual(instance.cloud_account, self.account)
        self.assertEqual(aws_instance.region, region)

        # Assert that the correct instance events were saved.
        # We expect to find *four* events. Note that "reboot" does not cause us
        # to generate a new event because we know it's already running.
        instanceevents = list(
            InstanceEvent.objects.filter(
                instance__aws_instance__ec2_instance_id=ec2_instance_id
            ).order_by("occurred_at")
        )

        self.assertEqual(len(instanceevents), 4)

        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[1].occurred_at, occurred_at_stop)
        self.assertEqual(instanceevents[2].occurred_at, occurred_at_modify)
        self.assertEqual(instanceevents[3].occurred_at, occurred_at_start)

        self.assertEqual(instanceevents[0].event_type, "power_on")
        self.assertEqual(instanceevents[1].event_type, "power_off")
        self.assertEqual(instanceevents[2].event_type, "attribute_change")
        self.assertEqual(instanceevents[3].event_type, "power_on")

        self.assertEqual(instanceevents[0].content_object.instance_type, instance_type)
        self.assertEqual(instanceevents[1].content_object.instance_type, None)
        self.assertEqual(
            instanceevents[2].content_object.instance_type, new_instance_type
        )
        self.assertEqual(instanceevents[3].content_object.instance_type, None)

        # Assert that as a side-effect two runs were created.
        runs = Run.objects.filter(instance=instance).order_by("start_time")
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
        self.assertEqual(image.owner_aws_account_id, described_image["OwnerId"])
        self.assertEqual(image.machine_image.get().status, MachineImage.PENDING)

    @util_helper.clouditardis(util_helper.utc_dt(2018, 1, 3, 0, 0, 0))
    @patch("api.tasks.calculate_max_concurrent_usage_task")
    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_instances")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_images")
    def test_analyze_log_run_instance_windows_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
        mock_calculate_concurrent_usage_task,
    ):
        """
        Analyze CloudTrail records for a Windows instance.

        Windows treatment is special because when we describe the image and
        discover that it has the "Windows" platform set, we save our model in
        an already-inspected state.
        """
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = util_helper.get_random_region()
        instance_type = util_helper.get_random_instance_type()

        ec2_instance_id = util_helper.generate_dummy_instance_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()

        # Define the mocked "describe images" behavior.
        described_image = util_helper.generate_dummy_describe_image(
            ec2_ami_id, platform="Windows"
        )
        described_images = {ec2_ami_id: described_image}

        def describe_images_side_effect(__, image_ids, ___):
            return [described_images[image_id] for image_id in image_ids]

        mock_describe_images.side_effect = describe_images_side_effect

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            "Records": [
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="RunInstances",
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                )
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        # We should *not* have described the instance because the CloudTrail
        # messages should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We *should* have described the image because it is new to us.
        mock_describe_images.assert_called()

        # Inspection should *not* have started for this new image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        instance = Instance.objects.get(aws_instance__ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.cloud_account, self.account)
        self.assertEqual(instance.content_object.region, region)

        # Assert that the correct instance event was saved.
        instanceevents = list(
            InstanceEvent.objects.filter(
                instance__aws_instance__ec2_instance_id=ec2_instance_id
            ).order_by("occurred_at")
        )
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[0].event_type, "power_on")
        self.assertEqual(instanceevents[0].content_object.instance_type, instance_type)

        # Assert that as a side-effect one run was created.
        runs = Run.objects.filter(instance=instance).order_by("start_time")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertIsNone(runs[0].end_time)

        # Assert that the correct image was saved.
        image = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
        self.assertEqual(image.region, region)
        self.assertEqual(image.owner_aws_account_id, described_image["OwnerId"])
        self.assertEqual(image.machine_image.get().status, MachineImage.INSPECTED)
        self.assertEqual(image.platform, image.WINDOWS)

    @util_helper.clouditardis(util_helper.utc_dt(2018, 1, 3, 0, 0, 0))
    @patch("api.tasks.calculate_max_concurrent_usage_task")
    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_instances")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_images")
    def test_analyze_log_run_instance_known_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
        mock_calculate_max_concurrent_usage_task,
    ):
        """
        Analyze CloudTrail records for a new instance with an image we know.

        In this case, we do *no* API describes and just process the CloudTrail
        record to save our model changes.
        """
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = util_helper.get_random_region()
        instance_type = util_helper.get_random_instance_type()

        ec2_instance_id = util_helper.generate_dummy_instance_id()
        known_image = helper.generate_image()
        ec2_ami_id = known_image.content_object.ec2_ami_id

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            "Records": [
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="RunInstances",
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                )
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        # We should *not* have described the instance because the CloudTrail
        # messages should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We should *not* have described the image because we already know it.
        mock_describe_images.assert_not_called()

        # Inspection should *not* have started for this existing image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        instance = Instance.objects.get(aws_instance__ec2_instance_id=ec2_instance_id)
        self.assertEqual(instance.cloud_account, self.account)
        self.assertEqual(instance.content_object.region, region)

        # Assert that the correct instance event was saved.
        instanceevents = list(
            InstanceEvent.objects.filter(
                instance__aws_instance__ec2_instance_id=ec2_instance_id
            ).order_by("occurred_at")
        )
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[0].event_type, "power_on")
        self.assertEqual(instanceevents[0].content_object.instance_type, instance_type)

        # Assert that as a side-effect one run was created.
        runs = Run.objects.filter(instance=instance).order_by("start_time")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertIsNone(runs[0].end_time)

    @util_helper.clouditardis(util_helper.utc_dt(2018, 1, 3, 0, 0, 0))
    @patch("api.tasks.calculate_max_concurrent_usage_task")
    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_instances")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_images")
    def test_analyze_log_start_old_instance_known_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
        mock_calculate_concurrent_usage_task,
    ):
        """
        Analyze CloudTrail records to start an instance with a known image.

        If an account had stopped a instance when it registered with us, we
        never see the "RunInstances" record for that instance. If it starts
        later with a "StartInstances" record, we don't receive enough
        information from the record alone and need to immediately describe the
        instance in AWS in order to populate our model.
        """
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = util_helper.get_random_region()

        image = helper.generate_image()
        ec2_ami_id = image.content_object.ec2_ami_id

        # Define the mocked "describe instances" behavior.
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        described_instance = util_helper.generate_dummy_describe_instance(
            instance_id=ec2_instance_id, image_id=ec2_ami_id
        )
        instance_type = described_instance["InstanceType"]
        described_instances = {ec2_instance_id: described_instance}

        def describe_instances_side_effect(__, instance_ids, ___):
            return dict(
                [
                    (instance_id, described_instances[instance_id])
                    for instance_id in instance_ids
                ]
            )

        mock_describe_instances.side_effect = describe_instances_side_effect

        # Define the S3 message payload.
        occurred_at_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            "Records": [
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="StartInstances",
                    event_time=occurred_at_start,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                )
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        # We *should* have described the instance because the CloudTrail record
        # should *not* have enough information to proceed.
        mock_describe_instances.assert_called()

        # We should *not* have described the image because we already know it.
        mock_describe_images.assert_not_called()

        # Inspection should *not* have started for this existing image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        awsinstance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        instance = awsinstance.instance.get()
        self.assertEqual(instance.cloud_account, self.account)
        self.assertEqual(awsinstance.region, region)

        # Assert that the correct instance event was saved.
        instanceevents = list(
            InstanceEvent.objects.filter(
                instance__aws_instance__ec2_instance_id=ec2_instance_id
            ).order_by("occurred_at")
        )
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_start)
        self.assertEqual(instanceevents[0].event_type, "power_on")
        self.assertEqual(instanceevents[0].content_object.instance_type, instance_type)

        # Assert that as a side-effect one run was created.
        runs = Run.objects.filter(instance=instance).order_by("start_time")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_start)
        self.assertIsNone(runs[0].end_time)

    @util_helper.clouditardis(util_helper.utc_dt(2018, 1, 3, 0, 0, 0))
    @patch("api.tasks.calculate_max_concurrent_usage_task")
    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_instances")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_images")
    def test_analyze_log_run_instance_unavailable_image(
        self,
        mock_describe_images,
        mock_describe_instances,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
        mock_calculate_concurrent_usage_task,
    ):
        """
        Analyze CloudTrail records for an instance with an unavailable image.

        This could happen if a user has deleted or revoked access to the AMI
        after starting the instance but before we could discover and process
        it. In that case, we save an image with status 'Unavailable' to
        indicate that we can't (and probably never will) inspect it.
        """
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        region = util_helper.get_random_region()

        instance_type = util_helper.get_random_instance_type()
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()

        # Define the mocked "describe images" behavior.
        mock_describe_images.return_value = []

        # Define the S3 message payload.
        occurred_at_run = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        s3_content = {
            "Records": [
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[ec2_instance_id],
                    event_name="RunInstances",
                    event_time=occurred_at_run,
                    region=region,
                    instance_type=instance_type,
                    image_id=ec2_ami_id,
                )
            ]
        }
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        # Assert that we deleted the message upon processing it.
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        # We should *not* have described the instance because the CloudTrail
        # record should have enough information to proceed.
        mock_describe_instances.assert_not_called()

        # We *should* have described the image because it is new to us.
        mock_describe_images.assert_called()

        # Inspection should *not* have started for this unavailable image.
        mock_inspection.assert_not_called()

        # Assert that the correct instance was saved.
        awsinstance = AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
        instance = awsinstance.instance.get()
        self.assertEqual(instance.cloud_account, self.account)
        self.assertEqual(awsinstance.region, region)

        # Assert that the correct instance events were saved.
        # We expect to find *four* events. Note that "reboot" does not cause us
        # to generate a new event because we know it's already running.
        instanceevents = list(
            InstanceEvent.objects.filter(
                instance__aws_instance__ec2_instance_id=ec2_instance_id
            ).order_by("occurred_at")
        )
        self.assertEqual(len(instanceevents), 1)
        self.assertEqual(instanceevents[0].occurred_at, occurred_at_run)
        self.assertEqual(instanceevents[0].event_type, "power_on")
        self.assertEqual(instanceevents[0].content_object.instance_type, instance_type)

        # Assert that as a side-effect two runs were created.
        runs = Run.objects.filter(instance=instance).order_by("start_time")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].instance_type, instance_type)
        self.assertEqual(runs[0].start_time, occurred_at_run)
        self.assertEqual(runs[0].end_time, None)

        # Assert that the correct image was saved.
        awsimage = AwsMachineImage.objects.get(ec2_ami_id=ec2_ami_id)
        image = awsimage.machine_image.get()
        self.assertEqual(awsimage.owner_aws_account_id, None)
        self.assertEqual(image.status, image.UNAVAILABLE)

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_with_multiple_sqs_messages(
        self, mock_receive, mock_s3, mock_del
    ):
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
            helper.generate_mock_cloudtrail_sqs_message(),
            helper.generate_mock_cloudtrail_sqs_message(),
            helper.generate_mock_cloudtrail_sqs_message(),
        ]
        mock_receive.return_value = sqs_messages
        simple_content = {"Records": []}
        mock_s3.side_effect = [
            json.dumps(simple_content),
            "hello world",  # invalid CloudTrail S3 log file content
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
        delete_1_call = call(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_messages[0]])
        delete_3_call = call(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_messages[2]])
        self.assertIn(delete_1_call, delete_message_calls)
        self.assertIn(delete_3_call, delete_message_calls)

    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_changed_instance_type_existing_instance(
        self, mock_receive, mock_s3, mock_del, mock_session, mock_inspection
    ):
        """
        Test that analyze_log correctly handles attribute change messages.

        This test focuses on just getting an instance attribute change message
        for an already known instance. Since we already know the instance,
        we do not need to make an extra describe instance call to AWS.
        """
        instance_type = "t1.potato"
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        gen_instance = helper.generate_instance(self.account, region="us-east-1")
        trail_record = helper.generate_cloudtrail_modify_instance_record(
            aws_account_id=self.aws_account_id,
            instance_id=gen_instance.content_object.ec2_instance_id,
            instance_type=instance_type,
            region="us-east-1",
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)
        mock_inspection.assert_not_called()
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 1)
        awsinstance = instances[0]
        instance = awsinstance.instance.get()
        self.assertEqual(
            awsinstance.ec2_instance_id,
            gen_instance.content_object.ec2_instance_id,
        )
        self.assertEqual(instance.cloud_account.id, self.account.id)

        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 1)
        awsevent = events[0]
        event = awsevent.instance_event.get()
        self.assertEqual(event.instance, instance)
        self.assertEqual(awsevent.instance_type, instance_type)
        self.assertEqual(event.event_type, "attribute_change")

    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_instances")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
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
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        described_instance = util_helper.generate_dummy_describe_instance()
        s3_content = {
            "Records": [
                helper.generate_cloudtrail_instances_record(
                    aws_account_id=self.aws_account_id,
                    instance_ids=[described_instance["InstanceId"]],
                    event_name="TerminateInstances",
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
        mock_del.assert_called_with(settings.AWS_CLOUDTRAIL_EVENT_URL, [sqs_message])

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 1)
        awsinstance = instances[0]
        instance = awsinstance.instance.get()
        self.assertEqual(awsinstance.ec2_instance_id, described_instance["InstanceId"])
        self.assertEqual(instance.cloud_account.id, self.account.id)

        # Note that the event is stored in a partially known state.
        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 1)
        awsevent = events[0]
        event = awsevent.instance_event.get()
        self.assertEqual(event.instance.content_object, awsinstance)
        self.assertEqual(event.instance, instance)
        self.assertIsNone(awsevent.subnet)
        self.assertIsNone(awsevent.instance_type)
        self.assertIsNone(event.instance.machine_image)

        # Note that no image is stored at all.
        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 0)

    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_when_account_is_not_known(
        self, mock_receive, mock_s3, mock_del, mock_session, mock_inspection
    ):
        """
        Test appropriate handling when the account ID in the log is unknown.

        This can happen when a user deletes their AWS role, deletes their
        cloudigrade account, and leave their cloudtrail running.

        The net effect of this is that the extracted parts of the message related
        to the unknown account return no new results, and the overall operation
        completes successfully with no new objects written to the database.
        """
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        trail_record = helper.generate_cloudtrail_instances_record(
            aws_account_id=util_helper.generate_dummy_aws_account_id(),
            instance_ids=[ec2_instance_id],
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)
        mock_inspection.assert_not_called()
        mock_del.assert_called()

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 0)
        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 0)
        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 0)

    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_when_account_is_disabled(
        self, mock_receive, mock_s3, mock_del, mock_session, mock_inspection
    ):
        """
        Test appropriate handling when the account ID in the log is disabled.

        This can happen if we receive a cloudtrail message after the related
        CloudAccount has been disabled.

        The expected result is similar to test_analyze_log_when_account_is_not_known.
        """
        self.account.is_enabled = False
        self.account.save()

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        trail_record = helper.generate_cloudtrail_instances_record(
            aws_account_id=self.aws_account_id,
            instance_ids=[ec2_instance_id],
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)
        mock_inspection.assert_not_called()
        mock_del.assert_called()

        instances = list(AwsInstance.objects.all())
        self.assertEqual(len(instances), 0)
        events = list(AwsInstanceEvent.objects.all())
        self.assertEqual(len(events), 0)
        images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(images), 0)

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_with_invalid_cloudtrail_log_content(
        self, mock_receive, mock_s3, mock_del
    ):
        """
        Test that a malformed (not JSON) log is not processed.

        This is a "supported" failure case. If somehow we cannot process the
        log file, the expected behavior is to log an exception message and not
        delete the SQS message that led us to that message. This means that the
        message would be picked up again and again with each task run. This is
        okay and expected, and we will (eventually) configure a DLQ to take any
        messages that we repeatedly fail to process.
        """
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = "hello world"

        successes, failures = tasks.analyze_log()
        self.assertEqual(len(successes), 0)
        self.assertEqual(len(failures), 1)

        mock_del.assert_not_called()

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail._process_cloudtrail_message")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_client_error_access_denied_logs_warning(
        self, mock_yield, mock_process, mock_del
    ):
        """Test that access denied ClientError is logged appropriately as WARNING."""
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}},
            operation_name=Mock(),
        )
        messages = [MagicMock()]
        mock_yield.return_value = messages
        mock_process.side_effect = client_error

        with self.assertLogs(
            "api.clouds.aws.tasks.cloudtrail", level="WARNING"
        ) as logging_watcher:
            successes, failures = tasks.analyze_log()
        self.assertEqual(len(successes), 0)
        self.assertEqual(failures, messages)
        mock_del.assert_not_called()

        self.assertIn(
            "Unexpected AWS AccessDenied in analyze_log",
            logging_watcher.records[0].message,
        )
        self.assertEqual(logging_watcher.records[0].levelname, "WARNING")
        self.assertIn(
            "Failed to process message id", logging_watcher.records[1].message
        )
        self.assertEqual(logging_watcher.records[1].levelname, "WARNING")

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail._process_cloudtrail_message")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_client_error_not_access_denied_logs_error(
        self, mock_yield, mock_process, mock_del
    ):
        """Test that other ClientError is logged appropriately as ERROR."""
        client_error = ClientError(
            error_response={"Error": {"Code": "SomethingOtherThanAccessDenied"}},
            operation_name=Mock(),
        )
        messages = [MagicMock()]
        mock_yield.return_value = messages
        mock_process.side_effect = client_error

        with self.assertLogs(
            "api.clouds.aws.tasks.cloudtrail", level="WARNING"
        ) as logging_watcher:
            successes, failures = tasks.analyze_log()
        self.assertEqual(len(successes), 0)
        self.assertEqual(failures, messages)
        mock_del.assert_not_called()

        self.assertIn(
            "Unexpected AWS SomethingOtherThanAccessDenied in analyze_log",
            logging_watcher.records[0].message,
        )
        self.assertEqual(logging_watcher.records[0].levelname, "ERROR")
        self.assertIn(
            "Failed to process message id", logging_watcher.records[1].message
        )
        self.assertEqual(logging_watcher.records[1].levelname, "ERROR")

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_analyze_log_with_irrelevant_log_activity(
        self, mock_receive, mock_s3, mock_del
    ):
        """Test that logs without relevant data are effectively ignored."""
        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        irrelevant_log = {
            "Records": [
                {"eventSource": "null.amazonaws.com"},
                {"errorCode": 123},
                {"eventName": "InvalidEvent"},
            ]
        }

        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(irrelevant_log)

        tasks.analyze_log()
        mock_del.assert_called()

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_ami_tags_added_success(self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags added."""
        ami = helper.generate_image()
        self.assertFalse(ami.openshift_detected)

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        trail_record = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[ami.content_object.ec2_ami_id],
            tag_names=[_faker.word(), aws.OPENSHIFT_TAG, _faker.word()],
            event_name=cloudtrail.CREATE_TAG,
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        updated_ami = AwsMachineImage.objects.get(
            ec2_ami_id=ami.content_object.ec2_ami_id
        )
        self.assertFalse(updated_ami.machine_image.get().rhel_detected_by_tag)
        self.assertTrue(updated_ami.machine_image.get().openshift_detected)
        mock_del.assert_called()

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_ami_tags_removed_success(self, mock_receive, mock_s3, mock_del):
        """Test processing a CloudTrail log for ami tags removed."""
        ami = helper.generate_image(rhel_detected_by_tag=True, openshift_detected=True)
        self.assertTrue(ami.rhel_detected_by_tag)
        self.assertTrue(ami.openshift_detected)

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        trail_record_1 = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[ami.content_object.ec2_ami_id],
            tag_names=[_faker.word(), aws.OPENSHIFT_TAG],
            event_name=cloudtrail.DELETE_TAG,
        )
        trail_record_2 = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[ami.content_object.ec2_ami_id],
            tag_names=[aws.RHEL_TAG, _faker.word()],
            event_name=cloudtrail.DELETE_TAG,
        )
        s3_content = {"Records": [trail_record_1, trail_record_2]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        updated_ami = AwsMachineImage.objects.get(
            ec2_ami_id=ami.content_object.ec2_ami_id
        )
        updated_image = updated_ami.machine_image.get()
        self.assertFalse(updated_image.rhel_detected_by_tag)
        self.assertFalse(updated_image.openshift_detected)
        mock_del.assert_called()

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_ami_multiple_tag_changes_success(self, mock_receive, mock_s3, mock_del):
        """
        Test processing a CloudTrail log for multiple ami tag changes.

        If we see that one of our tags is both added and removed within a set of logs,
        we only want to know about and save the most recent change.
        """
        ami = helper.generate_image(rhel_detected_by_tag=True)
        self.assertTrue(ami.rhel_detected_by_tag)

        first_record_time = get_now() - timedelta(minutes=10)
        second_record_time = first_record_time + timedelta(minutes=5)

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        trail_record_1 = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[ami.content_object.ec2_ami_id],
            tag_names=[_faker.word(), aws.RHEL_TAG],
            event_name=cloudtrail.DELETE_TAG,
            event_time=first_record_time,
        )
        trail_record_2 = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[ami.content_object.ec2_ami_id],
            tag_names=[aws.RHEL_TAG, _faker.word()],
            event_name=cloudtrail.CREATE_TAG,
            event_time=second_record_time,
        )
        s3_content = {"Records": [trail_record_1, trail_record_2]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        updated_ami = AwsMachineImage.objects.get(
            ec2_ami_id=ami.content_object.ec2_ami_id
        )
        updated_image = updated_ami.machine_image.get()
        self.assertTrue(updated_image.rhel_detected_by_tag)
        mock_del.assert_called()

    @patch("api.clouds.aws.tasks.cloudtrail.start_image_inspection")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_session")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.describe_images")
    def test_ami_tags_unknown_ami_is_added(
        self,
        mock_describe,
        mock_receive,
        mock_s3,
        mock_del,
        mock_session,
        mock_inspection,
    ):
        """
        Test processing a log for ami tags reference a new ami_id.

        In this case, we should attempt to describe the image and save it to
        our image model.
        """
        new_ami_id = util_helper.generate_dummy_image_id()
        image_data = util_helper.generate_dummy_describe_image(image_id=new_ami_id)
        mock_describe.return_value = [image_data]

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        region = util_helper.get_random_region()
        trail_record = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[new_ami_id],
            tag_names=[aws.OPENSHIFT_TAG],
            event_name=cloudtrail.CREATE_TAG,
            region=region,
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        new_ami = AwsMachineImage.objects.get(ec2_ami_id=new_ami_id)
        self.assertTrue(new_ami.machine_image.get().openshift_detected)
        mock_del.assert_called()
        mock_inspection.assert_called_once_with(
            self.account.content_object.account_arn, new_ami_id, region
        )

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_other_tags_ignored(self, mock_receive, mock_s3, mock_del):
        """
        Test tag processing where unknown tags should be ignored.

        In this case, the log data includes a new AMI ID. If we cared about the
        referenced tag, this operation would also describe that AMI and add it
        to our model database. However, since the tags in the log are not
        relevant to our interests, we should completely ignore the new AMI.
        """
        new_ami_id = util_helper.generate_dummy_image_id()

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        trail_record = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[new_ami_id],
            tag_names=[_faker.slug()],
            event_name=cloudtrail.CREATE_TAG,
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        all_images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(all_images), 0)
        mock_del.assert_called()

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_non_ami_resources_with_tags_ignored(self, mock_receive, mock_s3, mock_del):
        """Test tag processing where non-AMI resources should be ignored."""
        some_ignored_id = _faker.uuid4()

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        trail_record = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[some_ignored_id],
            tag_names=[_faker.slug()],
            event_name=cloudtrail.CREATE_TAG,
        )
        s3_content = {"Records": [trail_record]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        all_images = list(AwsMachineImage.objects.all())
        self.assertEqual(len(all_images), 0)
        mock_del.assert_called()

    @patch("api.clouds.aws.tasks.cloudtrail.aws.delete_messages_from_queue")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    @patch("api.clouds.aws.tasks.cloudtrail.aws.yield_messages_from_queue")
    def test_events_before_cloud_account_enabled_at_are_ignored(
        self, mock_receive, mock_s3, mock_del
    ):
        """Test ignoring events that occurred before CloudAccount.enabled_at."""
        event_time = util_helper.utc_dt(2019, 11, 1, 0, 0, 0)
        enabled_at = util_helper.utc_dt(2020, 2, 1, 0, 0, 0)
        self.account.enabled_at = enabled_at
        self.account.save()

        sqs_message = helper.generate_mock_cloudtrail_sqs_message()
        trail_record_instance = helper.generate_cloudtrail_instances_record(
            aws_account_id=self.aws_account_id,
            instance_ids=[util_helper.generate_dummy_instance_id()],
            event_name="RunInstances",
            event_time=event_time,
        )
        trail_record_image_tag = helper.generate_cloudtrail_tag_set_record(
            aws_account_id=self.aws_account_id,
            image_ids=[util_helper.generate_dummy_image_id()],
            tag_names=[_faker.word(), aws.OPENSHIFT_TAG, _faker.word()],
            event_name=cloudtrail.CREATE_TAG,
            event_time=event_time,
        )
        s3_content = {"Records": [trail_record_instance, trail_record_image_tag]}
        mock_receive.return_value = [sqs_message]
        mock_s3.return_value = json.dumps(s3_content)

        successes, failures = tasks.analyze_log()

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 0)

        all_images = list(AwsInstance.objects.all())
        self.assertEqual(len(all_images), 0)
        mock_del.assert_called()
