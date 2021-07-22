"""Collection of tests for the 'spawndata' management command."""
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.test import override_settings

from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
)
from api.clouds.azure.models import (
    AzureCloudAccount,
    AzureInstance,
    AzureInstanceEvent,
    AzureMachineImage,
)
from api.models import ConcurrentUsage, InstanceEvent, MachineImage, Run
from api.tests import helper as api_helper
from util.tests import helper as util_helper

user_join_datetime = util_helper.utc_dt(2019, 4, 15, 0, 0, 0)
command_run_datetime = util_helper.utc_dt(2019, 4, 20, 0, 0, 0)


class SpawnDataTest(TestCase):
    """Management command 'spawndata' test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        # Important note! Because recalculate_concurrent_usage_for_user_id checks the
        # User object's date_joined value when determining which days should calculate
        # but we are creating this User in setUp, unless we force an older date into the
        # User, spawndata will not calculate/save ConcurrentUsage objects as expected.
        self.user.date_joined = user_join_datetime
        self.user.save()
        api_helper.generate_instance_type_definitions()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @util_helper.clouditardis(command_run_datetime)
    @patch("util.management.commands.spawndata.random")
    @patch("util.management.commands.spawndata.tqdm")
    def test_command_output(self, mock_tqdm, mock_random):
        """Test that 'spawndata' correctly calls seeds data."""
        # Silence tqdm output during the test.
        mock_tqdm.side_effect = lambda iterable, *args, **kwargs: iterable

        # Make all random calculations deterministic.
        mock_random.choice.side_effect = lambda population: population[0]
        mock_random.random.return_value = 0.0
        mock_random.randrange.side_effect = lambda start, stop: (start + stop) / 2
        mock_random.gauss.side_effect = lambda mu, sigma: mu
        mock_random.uniform.side_effect = lambda a, b: (a + b) / 2

        call_command(
            "spawndata",
            "--account_count=1",
            "--image_count=5",
            "--instance_count=10",
            "--other_owner_chance=0.0",
            "--rhel_chance=1.0",
            "--ocp_chance=1.0",
            "--min_run_hours=1",
            "--mean_run_count=1",
            "--mean_hours_between_runs=1",
            "--confirm",
            self.user.id,
            user_join_datetime.strftime("%Y-%m-%d"),
        )

        self.assertEquals(AwsCloudAccount.objects.count(), 1)
        self.assertEquals(AwsMachineImage.objects.count(), 5)
        for image in MachineImage.objects.all():
            self.assertTrue(image.rhel)
            self.assertTrue(image.openshift)
        self.assertEquals(AwsInstance.objects.count(), 10)
        self.assertEquals(AwsInstanceEvent.objects.count(), 20)
        self.assertEqual(Run.objects.count(), 10)

        # 6 days inclusive between "user_join_date" 2019-04-15 and "today" 2019-04-20,
        # and 1 ConcurrentUsage per day means we expect 6 total.
        self.assertEqual(ConcurrentUsage.objects.count(), 6)

        # Verify all events were created between the start and "now".
        # Remember that clouditardis changed "now" to 2019-04-20.
        start_time_range = user_join_datetime
        end_time_range = command_run_datetime
        for event in InstanceEvent.objects.all():
            self.assertGreaterEqual(event.occurred_at, start_time_range)
            self.assertLess(event.occurred_at, end_time_range)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @util_helper.clouditardis(command_run_datetime)
    @patch("util.management.commands.spawndata.random")
    @patch("util.management.commands.spawndata.tqdm")
    def test_command_output_azure(self, mock_tqdm, mock_random):
        """Test that 'spawndata' correctly calls seeds data for azure account."""
        # Silence tqdm output during the test.
        mock_tqdm.side_effect = lambda iterable, *args, **kwargs: iterable

        # Make all random calculations deterministic.
        mock_random.choice.side_effect = lambda population: population[0]
        mock_random.random.return_value = 0.0
        mock_random.randrange.side_effect = lambda start, stop: (start + stop) / 2
        mock_random.gauss.side_effect = lambda mu, sigma: mu
        mock_random.uniform.side_effect = lambda a, b: (a + b) / 2

        call_command(
            "spawndata",
            "--cloud_type=azure",
            "--account_count=1",
            "--image_count=5",
            "--instance_count=10",
            "--other_owner_chance=0.0",
            "--rhel_chance=1.0",
            "--ocp_chance=1.0",
            "--min_run_hours=1",
            "--mean_run_count=1",
            "--mean_hours_between_runs=1",
            "--confirm",
            self.user.id,
            user_join_datetime.strftime("%Y-%m-%d"),
        )

        self.assertEquals(AzureCloudAccount.objects.count(), 1)
        self.assertEquals(AzureMachineImage.objects.count(), 5)
        for image in MachineImage.objects.all():
            self.assertTrue(image.rhel)
            self.assertTrue(image.openshift)
        self.assertEquals(AzureInstance.objects.count(), 10)
        self.assertEquals(AzureInstanceEvent.objects.count(), 20)
        self.assertEqual(Run.objects.count(), 10)

        # 6 days inclusive between "user_join_date" 2019-04-15 and "today" 2019-04-20,
        # and 1 ConcurrentUsage per day means we expect 6 total.
        self.assertEqual(ConcurrentUsage.objects.count(), 6)

        # Verify all events were created between the start and "now".
        # Remember that clouditardis changed "now" to 2019-04-20.
        start_time_range = user_join_datetime
        end_time_range = command_run_datetime
        for event in InstanceEvent.objects.all():
            self.assertGreaterEqual(event.occurred_at, start_time_range)
            self.assertLess(event.occurred_at, end_time_range)
