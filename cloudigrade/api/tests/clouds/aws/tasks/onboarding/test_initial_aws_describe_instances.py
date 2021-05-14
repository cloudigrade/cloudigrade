"""Collection of tests for aws.tasks.cloudtrail.initial_aws_describe_instances."""
import datetime
from unittest.mock import call, patch

from django.test import TestCase, TransactionTestCase

from api.clouds.aws import tasks
from api.clouds.aws.models import AwsInstance, AwsMachineImage
from api.clouds.aws.tasks.onboarding import aws
from api.models import (
    Instance,
    InstanceEvent,
    MachineImage,
    Run,
)
from api.tasks import process_instance_event
from api.tests import helper as account_helper
from util.tests import helper as util_helper


class InitialAwsDescribeInstancesTest(TestCase):
    """Celery task 'initial_aws_describe_instances' test cases."""

    @patch("api.tasks.calculate_max_concurrent_usage_task")
    @patch("api.clouds.aws.tasks.onboarding.start_image_inspection")
    @patch("api.clouds.aws.tasks.onboarding.aws")
    @patch("api.clouds.aws.util.aws")
    def test_initial_aws_describe_instances(
        self, mock_util_aws, mock_aws, mock_start, mock_calculate_concurrent_usage_task
    ):
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
        account = account_helper.generate_cloud_account()

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

        running_instances = [
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_unknown, state=aws.InstanceState.running
            ),
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_unknown, state=aws.InstanceState.running, no_subnet=True
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
        ]

        not_running_instances = [
            util_helper.generate_dummy_describe_instance(
                image_id=ami_id_gone, state=aws.InstanceState.terminated
            ),
        ]

        all_instances = running_instances + not_running_instances

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
            )
        ]

        tasks.initial_aws_describe_instances(account.id)
        mock_start.assert_has_calls(start_inspection_calls)

        # Verify that we created all five instances.
        instances_count = Instance.objects.filter(cloud_account=account).count()
        self.assertEqual(instances_count, len(all_instances))

        # Verify that the running instances exist with power-on events.
        for described_instance in running_instances:
            instance_id = described_instance["InstanceId"]
            aws_instance = AwsInstance.objects.get(ec2_instance_id=instance_id)
            self.assertIsInstance(aws_instance, AwsInstance)
            self.assertEqual(region, aws_instance.region)
            event = InstanceEvent.objects.get(instance=aws_instance.instance.get())
            self.assertIsInstance(event, InstanceEvent)
            self.assertEqual(InstanceEvent.TYPE.power_on, event.event_type)

        # Verify that the not-running instances exist with no events.
        for described_instance in not_running_instances:
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

    @patch("api.clouds.aws.tasks.onboarding.aws")
    def test_initial_aws_describe_instances_missing_account(self, mock_aws):
        """Test early return when account does not exist."""
        account_id = -1  # negative number account ID should never exist.
        tasks.initial_aws_describe_instances(account_id)
        mock_aws.get_session.assert_not_called()

    @patch("api.clouds.aws.tasks.onboarding.aws")
    def test_initial_aws_describe_instances_account_disabled(self, mock_aws):
        """Test early return when account exists but is disabled."""
        account = account_helper.generate_cloud_account(is_enabled=False)
        tasks.initial_aws_describe_instances(account.id)
        mock_aws.get_session.assert_not_called()


class InitialAwsDescribeInstancesPowerOffNotRunningTest(TestCase):
    """
    Test cases for 'initial_aws_describe_instances' creating power_off events.

    This asserts expected behavior when we actually already have some instance for
    the given cloud account and that instance's most recent power-related event
    indicates it was powered on. When we perform the "describe" operation, if that
    instance is absent or not running, we immediately generate a power-off event
    since it's likely that we failed to process the relevant CloudTrail log.
    """

    def setUp(self):
        """Set up data for an account with a running instance."""
        self.account = account_helper.generate_cloud_account()
        self.instance = account_helper.generate_instance(self.account)
        self.aws_instance = self.instance.content_object
        self.region = self.aws_instance.region
        self.power_on_time = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.power_off_time = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        event = account_helper.generate_single_instance_event(
            self.instance, self.power_on_time, event_type=InstanceEvent.TYPE.power_on
        )
        self.process_event(event)

    def process_event(self, event):
        """Process the event but skip the async calculate max concurrent function."""
        with patch(
            "api.tasks.calculate_max_concurrent_usage_from_runs"
        ) as mock_calculate_max_concurrent:
            process_instance_event(event)
            if event.event_type == InstanceEvent.TYPE.power_on:
                mock_calculate_max_concurrent.assert_called()

    def assertExpectedEventsAndRun(self):
        """Assert known instance has exactly one run and two power_on/off events."""
        events = InstanceEvent.objects.filter(instance=self.instance).order_by(
            "occurred_at"
        )
        self.assertEqual(events.count(), 2)
        # The first was the old power_on, and the second is the new power_off.
        self.assertEqual(events[0].event_type, InstanceEvent.TYPE.power_on)
        self.assertEqual(events[1].event_type, InstanceEvent.TYPE.power_off)

        runs = Run.objects.filter(instance=self.instance)
        self.assertEqual(runs.count(), 1)
        run = runs.first()
        self.assertEqual(run.start_time, self.power_on_time)
        self.assertIsNotNone(run.end_time, self.power_off_time)

    @patch("api.util.calculate_max_concurrent_usage_from_runs")
    @patch("api.clouds.aws.tasks.onboarding.aws")
    def test_power_off_not_present(self, mock_aws, mock_calculate_max_concurrent):
        """Create power_off event for running instance not present in the describe."""
        described_instances = {}  # empty means no instances found.
        mock_aws.describe_instances_everywhere.return_value = described_instances

        with util_helper.clouditardis(self.power_off_time):
            tasks.initial_aws_describe_instances(self.account.id)

        mock_calculate_max_concurrent.assert_called()
        self.assertExpectedEventsAndRun()

    @patch("api.util.calculate_max_concurrent_usage_from_runs")
    @patch("api.clouds.aws.tasks.onboarding.aws")
    def test_instance_found_not_running(self, mock_aws, mock_calculate_max_concurrent):
        """Create power_off event for instance found stopped in the describe."""
        described_instances = {
            self.region: [
                util_helper.generate_dummy_describe_instance(
                    instance_id=self.aws_instance.ec2_instance_id,
                    state=aws.InstanceState.stopped,
                )
            ]
        }
        mock_aws.describe_instances_everywhere.return_value = described_instances

        with util_helper.clouditardis(self.power_off_time):
            tasks.initial_aws_describe_instances(self.account.id)

        mock_calculate_max_concurrent.assert_called()
        self.assertExpectedEventsAndRun()

    @patch("api.util.calculate_max_concurrent_usage_from_runs")
    @patch("api.clouds.aws.tasks.onboarding.aws")
    def test_instance_already_power_off(self, mock_aws, mock_calculate_max_concurrent):
        """Don't create power_off for instance that already has recent power_off."""
        event = account_helper.generate_single_instance_event(
            self.instance, self.power_off_time, event_type=InstanceEvent.TYPE.power_off
        )
        self.process_event(event)
        mock_calculate_max_concurrent.reset_mock()

        described_instances = {
            self.region: [
                util_helper.generate_dummy_describe_instance(
                    instance_id=self.aws_instance.ec2_instance_id,
                    state=aws.InstanceState.stopped,
                )
            ]
        }
        mock_aws.describe_instances_everywhere.return_value = described_instances

        describe_time = self.power_off_time + datetime.timedelta(days=1)
        with util_helper.clouditardis(describe_time):
            tasks.initial_aws_describe_instances(self.account.id)

        mock_calculate_max_concurrent.assert_not_called()
        self.assertExpectedEventsAndRun()


class InitialAwsDescribeInstancesTransactionTest(TransactionTestCase):
    """Test cases for 'initial_aws_describe_instances', but with transactions."""

    @patch("api.util.schedule_concurrent_calculation_task")
    @patch("api.models.sources.notify_application_availability")
    @patch("api.clouds.aws.tasks.onboarding.start_image_inspection")
    @patch("api.clouds.aws.tasks.onboarding.aws")
    @patch("api.clouds.aws.util.aws")
    def test_initial_aws_describe_instances_twice(
        self,
        mock_util_aws,
        mock_aws,
        mock_start,
        mock_sources_notify,
        mock_schedule_concurrent_calculation_task,
    ):
        """
        Test calling initial_aws_describe_instances twice with no data changes.

        This test asserts appropriate behavior if we call account.enable after
        performing the initial AWS account describe once but without generating any new
        activity after the initial describe. This is likely to happen for AWS accounts
        with any long-running instances that have not changed state since the last time
        account.enable was called. Since our account availability checks routinely call
        account.enable to verify permissions, we need to test handling this use case.

        Why is this a concern? We used to naively *always* insert a new InstanceEvent
        for a running instance seen within initial_aws_describe_instances. That's not a
        problem in isolation; the new event would result in the runs being recreated and
        concurrent usage being recalculated. However, this becomes a problem if the
        instance's run spans many days (meaning many more recalculations) or if the
        account.enable function (which also calls initial_aws_describe_instances) is
        being called frequently, which may be the case since we cannot control when
        external callers hit an account's availability_check endpoint.

        A resolution to this concern is to perform an existence check before allowing
        initial_aws_describe_instances to insert a new InstanceEvent. If the most recent
        event is power_on, then we don't need to store another power_on, and we don't
        need to rebuild the run and recalculate concurrent usages. The updated expected
        behavior of calling account.enable shortly after initial_aws_describe_instances
        is that no new InstantEvent objects will be created by account.enable if a
        running described instance's most recent event is power_on.
        """
        account = account_helper.generate_cloud_account()

        # Set up mocked data in AWS API responses.
        region = util_helper.get_random_region()
        described_ami = util_helper.generate_dummy_describe_image()
        ec2_ami_id = described_ami["ImageId"]
        described_instance = util_helper.generate_dummy_describe_instance(
            image_id=ec2_ami_id, state=aws.InstanceState.running
        )
        ec2_instance_id = described_instance["InstanceId"]
        described_instances = {region: [described_instance]}
        mock_aws.describe_instances_everywhere.return_value = described_instances
        mock_util_aws.describe_images.return_value = [described_ami]
        mock_util_aws.is_windows.side_effect = aws.is_windows
        mock_util_aws.InstanceState.is_running = aws.InstanceState.is_running
        mock_util_aws.AwsArn = aws.AwsArn
        mock_util_aws.verify_account_access.return_value = True, []

        date_of_initial_describe = util_helper.utc_dt(2020, 3, 1, 0, 0, 0)
        date_of_redundant_enable = util_helper.utc_dt(2020, 3, 2, 0, 0, 0)

        with util_helper.clouditardis(date_of_initial_describe):
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_called_with(
                account.content_object.account_arn, ec2_ami_id, region
            )
            mock_schedule_concurrent_calculation_task.assert_called()

        # Reset because we need to check these mocks again later.
        mock_schedule_concurrent_calculation_task.reset_mock()
        mock_start.reset_mock()

        with patch.object(
            tasks, "initial_aws_describe_instances"
        ) as mock_initial, util_helper.clouditardis(date_of_redundant_enable):
            # Even though we want to test initial_aws_describe_instances, we need to
            # mock this particular call because we need to short-circuit Celery.
            account.enable()
            mock_initial.delay.assert_called()
            mock_sources_notify.assert_called()

        with util_helper.clouditardis(date_of_redundant_enable):
            tasks.initial_aws_describe_instances(account.id)
            # start_image_inspection should not be called because we already know
            # about the image from the earlier initial_aws_describe_instances call.
            mock_start.assert_not_called()
            # schedule_concurrent_calculation_task should not be called because we
            # should not have generated any new events here that would require it.
            mock_schedule_concurrent_calculation_task.assert_not_called()

        # The relevant describe and account.enable processing is now done.
        # Now we just need to assert that we did not create redundant power_on events.
        instance_events = (
            AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
            .instance.get()
            .instanceevent_set.order_by("occurred_at")
        )
        self.assertEqual(instance_events.count(), 1)
        instance_event = instance_events.first()
        self.assertEqual(instance_event.occurred_at, date_of_initial_describe)
        self.assertEqual(instance_event.event_type, InstanceEvent.TYPE.power_on)

    @patch("api.util.schedule_concurrent_calculation_task")
    @patch("api.models.sources.notify_application_availability")
    @patch("api.clouds.aws.tasks.onboarding.start_image_inspection")
    @patch("api.clouds.aws.tasks.onboarding.aws")
    @patch("api.clouds.aws.util.aws")
    def test_initial_aws_describe_instances_after_disable_enable(
        self,
        mock_util_aws,
        mock_aws,
        mock_start,
        mock_sources_notify,
        mock_schedule_concurrent_calculation_task,
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
        account = account_helper.generate_cloud_account()

        # Set up mocked data in AWS API responses.
        region = util_helper.get_random_region()

        described_ami = util_helper.generate_dummy_describe_image()
        ec2_ami_id = described_ami["ImageId"]
        described_instance = util_helper.generate_dummy_describe_instance(
            image_id=ec2_ami_id, state=aws.InstanceState.running
        )
        ec2_instance_id = described_instance["InstanceId"]
        described_instances = {region: [described_instance]}
        mock_aws.describe_instances_everywhere.return_value = described_instances
        mock_util_aws.describe_images.return_value = [described_ami]
        mock_util_aws.is_windows.side_effect = aws.is_windows
        mock_util_aws.InstanceState.is_running = aws.InstanceState.is_running
        mock_util_aws.AwsArn = aws.AwsArn
        mock_util_aws.verify_account_access.return_value = True, []

        date_of_initial_describe = util_helper.utc_dt(2020, 3, 1, 0, 0, 0)
        date_of_disable = util_helper.utc_dt(2020, 3, 2, 0, 0, 0)
        date_of_reenable = util_helper.utc_dt(2020, 3, 3, 0, 0, 0)

        with util_helper.clouditardis(date_of_initial_describe):
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_called_with(
                account.content_object.account_arn, ec2_ami_id, region
            )
            mock_schedule_concurrent_calculation_task.assert_called()

        # Reset because we need to check these mocks again later.
        mock_schedule_concurrent_calculation_task.reset_mock()
        mock_start.reset_mock()

        with util_helper.clouditardis(date_of_disable):
            account.disable()
            mock_util_aws.delete_cloudtrail.assert_called()

        # Before calling "start_image_inspection" again, let's change the mocked return
        # values from AWS to include another instance and image. We should ultimately
        # expect the original instance + ami to be found but *not* describe its image.
        # Only the new instance + ami should be fully described.

        described_ami_2 = util_helper.generate_dummy_describe_image()
        ec2_ami_id_2 = described_ami_2["ImageId"]
        described_instance_2 = util_helper.generate_dummy_describe_instance(
            image_id=ec2_ami_id_2, state=aws.InstanceState.running
        )
        ec2_instance_id_2 = described_instance_2["InstanceId"]
        described_instances = {region: [described_instance, described_instance_2]}
        mock_aws.describe_instances_everywhere.return_value = described_instances
        mock_util_aws.describe_images.return_value = [described_ami, described_ami_2]

        with patch.object(
            tasks, "initial_aws_describe_instances"
        ) as mock_initial, util_helper.clouditardis(date_of_reenable):
            # Even though we want to test initial_aws_describe_instances, we need to
            # mock this particular call because we need to short-circuit Celery.
            account.enable()
            mock_sources_notify.assert_called()
            mock_initial.delay.assert_called()

        with util_helper.clouditardis(date_of_reenable):
            tasks.initial_aws_describe_instances(account.id)
            mock_start.assert_called_with(
                account.content_object.account_arn, ec2_ami_id_2, region
            )
            mock_schedule_concurrent_calculation_task.assert_called()

        # Now that the dust has settled, let's check that the two instances have events
        # in the right configuration. The first instance is on, off, and on; the second
        # instance is on.

        instance_1_events = (
            AwsInstance.objects.get(ec2_instance_id=ec2_instance_id)
            .instance.get()
            .instanceevent_set.order_by("occurred_at")
        )
        self.assertEqual(instance_1_events.count(), 3)
        instance_1_event_1 = instance_1_events[0]
        self.assertEqual(instance_1_event_1.occurred_at, date_of_initial_describe)
        self.assertEqual(instance_1_event_1.event_type, InstanceEvent.TYPE.power_on)
        instance_1_event_2 = instance_1_events[1]
        self.assertEqual(instance_1_event_2.occurred_at, date_of_disable)
        self.assertEqual(instance_1_event_2.event_type, InstanceEvent.TYPE.power_off)
        instance_1_event_3 = instance_1_events[2]
        self.assertEqual(instance_1_event_3.occurred_at, date_of_reenable)
        self.assertEqual(instance_1_event_3.event_type, InstanceEvent.TYPE.power_on)

        instance_2_events = (
            AwsInstance.objects.get(ec2_instance_id=ec2_instance_id_2)
            .instance.get()
            .instanceevent_set.order_by("occurred_at")
        )
        self.assertEqual(instance_2_events.count(), 1)
        instance_2_event_1 = instance_2_events[0]
        self.assertEqual(instance_2_event_1.occurred_at, date_of_reenable)
        self.assertEqual(instance_2_event_1.event_type, InstanceEvent.TYPE.power_on)
