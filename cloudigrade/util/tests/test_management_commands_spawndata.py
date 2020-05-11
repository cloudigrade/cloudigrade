"""Collection of tests for the 'spawndata' management command."""
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
)
from api.models import InstanceEvent, MachineImage
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class SpawnDataTest(TestCase):
    """Management command 'spawndata' test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        api_helper.generate_aws_ec2_definitions()

    @util_helper.clouditardis(util_helper.utc_dt(2019, 4, 20, 0, 0, 0))
    @patch("util.management.commands.spawndata.random")
    @patch("util.management.commands.spawndata.tqdm")
    @patch("util.management.commands.spawndata.call_command")
    def test_command_output(self, mock_call_command, mock_tqdm, mock_random):
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
            "1",
            "2019-04-15",
        )

        mock_call_command.assert_called_with("create_runs", "--confirm")

        self.assertEquals(AwsCloudAccount.objects.count(), 1)
        self.assertEquals(AwsMachineImage.objects.count(), 5)
        for image in MachineImage.objects.all():
            self.assertTrue(image.rhel)
            self.assertTrue(image.openshift)
        self.assertEquals(AwsInstance.objects.count(), 10)
        self.assertEquals(AwsInstanceEvent.objects.count(), 20)

        # Verify all events were created between the start and "now".
        # Remember that clouditardis changed "now" to 2019-04-20.
        start_time_range = util_helper.utc_dt(2019, 4, 15)
        end_time_range = util_helper.utc_dt(2019, 4, 20)
        for event in InstanceEvent.objects.all():
            self.assertGreaterEqual(event.occurred_at, start_time_range)
            self.assertLess(event.occurred_at, end_time_range)
