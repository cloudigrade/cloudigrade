"""Collection of tests for the 'create_runs' management command."""
from unittest.mock import patch

import faker
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from api import models
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class CreateRunsTest(TestCase):
    """Management command 'create_runs' test case."""

    def setUp(self):
        """Set up test data."""
        self.user = util_helper.generate_test_user()
        self.account = api_helper.generate_cloud_account(user=self.user)
        self.image_rhel = api_helper.generate_image(rhel_detected=True)
        self.instance = api_helper.generate_instance(
            self.account, image=self.image_rhel
        )
        self.instance_type = "c5.xlarge"  # 4 vcpu and 8.0 memory
        self.factory = APIRequestFactory()
        self.faker = faker.Faker()

        api_helper.generate_single_run(
            self.instance,
            (
                util_helper.utc_dt(2019, 3, 15, 1, 0, 0),
                util_helper.utc_dt(2019, 3, 15, 2, 0, 0),
            ),
            image=self.instance.machine_image,
            instance_type=self.instance_type,
        )

    def get_first_run(self):
        """Get the Run with the first/oldest start time."""
        return models.Run.objects.order_by("start_time").first()

    def assertRunsEqual(self, run_a, run_b):
        """Assert that two runs have effectively equal content."""
        self.assertEqual(run_a.instance, run_b.instance)
        self.assertEqual(run_a.start_time, run_b.start_time)
        self.assertEqual(run_a.end_time, run_b.end_time)

    def assertCreateRunsCompleted(self, old_run):
        """Assert the create_runs command had expected effects on models."""
        run = self.get_first_run()
        self.assertRunsEqual(run, old_run)
        with self.assertRaises(models.Run.DoesNotExist):
            # expect this to fail because the old run should have been deleted.
            old_run.refresh_from_db()
        self.assertEqual(models.Run.objects.all().count(), 1)
        self.assertEqual(models.ConcurrentUsage.objects.all().count(), 0)

    def assertCreateRunsAborted(self, old_run):
        """Assert the create_runs command had no effects on models due to abortion."""
        run = self.get_first_run()
        self.assertRunsEqual(run, old_run)
        old_run.refresh_from_db()  # refresh should work; old run should not be deleted.
        self.assertEqual(models.Run.objects.all().count(), 1)
        self.assertEqual(models.ConcurrentUsage.objects.all().count(), 1)

    @patch(
        "util.management.commands.create_runs.calculate_max_concurrent_usage_from_runs"
    )
    def test_handle_confirm_flag(self, mock_calculate):
        """Test calling create_runs with confirm arg."""
        old_run = self.get_first_run()
        call_command("create_runs", "--confirm")
        self.assertCreateRunsCompleted(old_run)
        mock_calculate.assert_called_with([self.get_first_run()])

    @patch(
        "util.management.commands.create_runs.calculate_max_concurrent_usage_from_runs"
    )
    @patch("util.management.commands.create_runs.input", return_value="N")
    def test_handle_input_no(self, mock_input, mock_calculate):
        """Test calling create_runs with "N" no input."""
        old_run = self.get_first_run()
        call_command("create_runs")
        self.assertCreateRunsAborted(old_run)
        mock_calculate.assert_not_called()

    @patch(
        "util.management.commands.create_runs.calculate_max_concurrent_usage_from_runs"
    )
    @patch("util.management.commands.create_runs.input", return_value="Y")
    def test_handle_input_yes(self, mock_input, mock_calculate):
        """Test calling create_runs with "Y" yes input."""
        old_run = models.Run.objects.first()
        call_command("create_runs")
        self.assertCreateRunsCompleted(old_run)
        mock_calculate.assert_called_with([self.get_first_run()])
