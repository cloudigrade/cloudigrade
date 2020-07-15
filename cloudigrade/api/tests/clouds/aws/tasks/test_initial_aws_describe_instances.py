"""Collection of tests for tasks.initial_aws_describe_instances."""
from unittest.mock import call, patch

from django.test import TestCase, TransactionTestCase

from api.clouds.aws import tasks
from api.clouds.aws.models import AwsInstance, AwsMachineImage
from api.clouds.aws.tasks import aws
from api.models import (
    Instance,
    InstanceEvent,
    MachineImage,
)
from api.tests import helper as account_helper
from util.tests import helper as util_helper


class InitialAwsDescribeInstancesTest(TestCase):
    """Celery task 'initial_aws_describe_instances' test cases."""

    @patch("api.clouds.aws.tasks.aws")
    @patch("api.clouds.aws.util.aws")
    def test_initial_aws_describe_instances(self, mock_util_aws, mock_aws):
        """
        Test happy-path behaviors of initial_aws_describe_instances.

        This test simulates a situation in which three running instances are
        found. One instance has the Windows platform, another instance has its
        image tagged for OpenShift, and a third instance has neither of those.

        The end result is that the three running instances should be saved,
        three power-on events should be saved (one for each instance), three
        images should be saved, and two new tasks should be spawned for
        inspecting the two not-windows images.
        """
        account = account_helper.generate_aws_account()

        # Set up mocked data in AWS API responses.
        region = util_helper.get_random_region()
        described_ami_unknown = util_helper.generate_dummy_describe_image()
        described_ami_openshift = util_helper.generate_dummy_describe_image(
            openshift=True
        )
        described_ami_windows = util_helper.generate_dummy_describe_image()

        ami_id_unknown = described_ami_unknown["ImageId"]
        ami_id_openshift = described_ami_openshift["ImageId"]
        ami_id_windows = described_ami_windows["ImageId"]
        ami_id_unavailable = util_helper.generate_dummy_image_id()
        ami_id_gone = util_helper.generate_dummy_image_id()

        all_instances = [
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_unknown, state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_openshift, state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_windows,
                state=aws.InstanceState.running,
                platform=AwsMachineImage.WINDOWS,
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_unavailable, state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_gone, state=aws.InstanceState.terminated
            ),
        ]
        described_instances = {region: all_instances}

        mock_aws.describe_instances_everywhere.return_value = described_instances
        mock_util_aws.describe_images.return_value = [
            described_ami_unknown,
            described_ami_openshift,
            described_ami_windows,
        ]
        mock_util_aws.is_windows.side_effect = aws.is_windows
        mock_util_aws.OPENSHIFT_TAG = aws.OPENSHIFT_TAG
        mock_util_aws.InstanceState.is_running = aws.InstanceState.is_running

        start_inspection_calls = [
            call(
                account.content_object.account_arn,
                described_ami_unknown["ImageId"],
                region,
            ),
            call(
                account.content_object.account_arn,
                described_ami_openshift["ImageId"],
                region,
            ),
        ]

        with patch.object(tasks, "start_image_inspection") as mock_start:
            # with patch("api.clouds.aws.tasks.start_image_inspection") as mock_start:
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_has_calls(start_inspection_calls)

        # Verify that we created all five instances.
        instances_count = Instance.objects.filter(cloud_account=account).count()
        self.assertEqual(instances_count, 5)

        # Verify that the running instances exist with power-on events.
        for described_instance in all_instances[:4]:
            instance_id = described_instance["InstanceId"]
            aws_instance = AwsInstance.objects.get(ec2_instance_id=instance_id)
            self.assertIsInstance(aws_instance, AwsInstance)
            self.assertEqual(region, aws_instance.region)
            event = InstanceEvent.objects.get(instance=aws_instance.instance.get())
            self.assertIsInstance(event, InstanceEvent)
            self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

        # Verify that the not-running instances exist with no events.
        for described_instance in all_instances[4:]:
            instance_id = described_instance["InstanceId"]
            aws_instance = AwsInstance.objects.get(ec2_instance_id=instance_id)
            self.assertIsInstance(aws_instance, AwsInstance)
            self.assertEqual(region, aws_instance.region)
            self.assertFalse(
                InstanceEvent.objects.filter(
                    instance=aws_instance.instance.get()
                ).exists()
            )

        # Verify that we saved images for all instances, even if not running.
        images_count = AwsMachineImage.objects.count()
        self.assertEqual(images_count, 5)

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_unknown)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertEqual(image.name, described_ami_unknown["Name"])

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_openshift)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertTrue(image.openshift_detected)
        self.assertEqual(image.name, described_ami_openshift["Name"])

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_windows)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertEqual(image.name, described_ami_windows["Name"])
        self.assertEqual(aws_image.platform, AwsMachineImage.WINDOWS)

        aws_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id_unavailable)
        image = aws_image.machine_image.get()
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertEqual(image.status, MachineImage.UNAVAILABLE)

    @patch("api.clouds.aws.tasks.aws")
    def test_initial_aws_describe_instances_missing_account(self, mock_aws):
        """Test early return when account does not exist."""
        account_id = -1  # negative number account ID should never exist.
        tasks.initial_aws_describe_instances(account_id)
        mock_aws.get_session.assert_not_called()

    @patch("api.clouds.aws.tasks.aws")
    def test_initial_aws_describe_instances_account_disabled(self, mock_aws):
        """Test early return when account exists but is disabled."""
        account = account_helper.generate_aws_account(is_enabled=False)
        tasks.initial_aws_describe_instances(account.id)
        mock_aws.get_session.assert_not_called()


class InitialAwsDescribeInstancesTransactionTest(TransactionTestCase):
    """Test cases for 'initial_aws_describe_instances', but with transactions."""

    @patch("api.models.notify_sources_application_availability")
    @patch("api.clouds.aws.tasks.aws")
    @patch("api.clouds.aws.util.aws")
    def test_initial_aws_describe_instances_after_disable_enable(
        self, mock_util_aws, mock_aws, mock_sources_notify
    ):
        """
        Test calling initial_aws_describe_instances multiple times.

        Historically (and in the simplified ideal happy-path), we would only ever call
        initial_aws_describe_instances exactly once when an AwsCloudAccount was first
        created. However, since we added support to disable accounts, it's now possible
        (and likely common) for an account to be created (and enabled), call describe,
        be disabled, be enabled again, and call describe again during the enable.

        We need to ensure that running described instances that generated "power_off"
        InstanceEvents as a result of AwsCloudAccount.disable would later correctly get
        new "power_on" InstanceEvents as a result of AwsCloudAccount.enable.
        """
        account = account_helper.generate_aws_account()

        # Set up mocked data in AWS API responses.
        region = util_helper.get_random_region()

        described_ami = util_helper.generate_dummy_describe_image()
        ami_id = described_ami["ImageId"]
        all_instances = [
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id, state=aws.InstanceState.running
            ),
        ]
        described_instances = {region: all_instances}
        mock_aws.describe_instances_everywhere.return_value = described_instances
        mock_util_aws.describe_images.return_value = [described_ami]
        mock_util_aws.is_windows.side_effect = aws.is_windows
        mock_util_aws.InstanceState.is_running = aws.InstanceState.is_running
        mock_util_aws.AwsArn = aws.AwsArn
        mock_util_aws.verify_account_access.return_value = True, []

        inspection_call = call(
            account.content_object.account_arn, described_ami["ImageId"], region,
        )

        date_of_initial_describe = util_helper.utc_dt(2020, 3, 1, 0, 0, 0)
        date_of_disable = util_helper.utc_dt(2020, 3, 2, 0, 0, 0)
        date_of_reenable = util_helper.utc_dt(2020, 3, 3, 0, 0, 0)

        with patch.object(
            tasks, "start_image_inspection"
        ) as mock_start, util_helper.clouditardis(date_of_initial_describe,):
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_has_calls([inspection_call])

        with util_helper.clouditardis(date_of_disable):
            account.disable()
            mock_util_aws.delete_cloudtrail.assert_called()

        # Before calling "start_image_inspection" again, let's change the mocked return
        # values from AWS to include another instance and image. We should ultimately
        # expect the original instance + ami to be found but *not* describe its image.
        # Only the new instance + ami should be fully described.

        described_ami_2 = util_helper.generate_dummy_describe_image()
        ami_id_2 = described_ami_2["ImageId"]
        all_instances.append(
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_2, state=aws.InstanceState.running
            )
        )
        described_instances = {region: all_instances}
        mock_aws.describe_instances_everywhere.return_value = described_instances
        mock_util_aws.describe_images.return_value = [described_ami, described_ami_2]

        inspection_call_2 = call(
            account.content_object.account_arn, described_ami_2["ImageId"], region,
        )

        with patch.object(
            tasks, "initial_aws_describe_instances"
        ) as mock_initial, util_helper.clouditardis(date_of_reenable):
            # Even though we want to test initial_aws_describe_instances, we need to
            # mock this particular call because we need to short-circuit Celery.
            account.enable()
            mock_initial.delay.assert_called()

        with patch.object(
            tasks, "start_image_inspection"
        ) as mock_start, util_helper.clouditardis(date_of_reenable):
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_has_calls([inspection_call_2])

        # Now that the dust has settled, let's check that the two instances have events
        # in the right configuration. The first instance is on, off, and on; the second
        # instance is on.

        aws_instance_1_events = (
            AwsInstance.objects.get(ec2_instance_id=all_instances[0]["InstanceId"])
            .instance.get()
            .instanceevent_set.order_by("occurred_at")
            .all()
        )
        self.assertEqual(len(aws_instance_1_events), 3)
        instance_1_event_1 = aws_instance_1_events[0]
        self.assertEqual(instance_1_event_1.occurred_at, date_of_initial_describe)
        self.assertEqual(instance_1_event_1.event_type, InstanceEvent.TYPE.power_on)
        instance_1_event_2 = aws_instance_1_events[1]
        self.assertEqual(instance_1_event_2.occurred_at, date_of_disable)
        self.assertEqual(instance_1_event_2.event_type, InstanceEvent.TYPE.power_off)
        instance_1_event_3 = aws_instance_1_events[2]
        self.assertEqual(instance_1_event_3.occurred_at, date_of_reenable)
        self.assertEqual(instance_1_event_3.event_type, InstanceEvent.TYPE.power_on)

        aws_instance_2_events = (
            AwsInstance.objects.get(ec2_instance_id=all_instances[1]["InstanceId"])
            .instance.get()
            .instanceevent_set.order_by("occurred_at")
            .all()
        )
        self.assertEqual(len(aws_instance_2_events), 1)
        instance_2_event_1 = aws_instance_2_events[0]
        self.assertEqual(instance_2_event_1.occurred_at, date_of_reenable)
        self.assertEqual(instance_2_event_1.event_type, InstanceEvent.TYPE.power_on)
