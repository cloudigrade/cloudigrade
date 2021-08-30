"""Collection of tests for tasks.calculation.fix_problematic_runs."""
import datetime
from unittest.mock import call, patch

from django.test import TestCase

from api import models
from api.tasks import calculation
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class FixProblematicRunsTest(TestCase):
    """Test case for Celery task fix_problematic_runs."""

    @patch("api.tasks.calculation._fix_problematic_run")
    def test_fix_problematic_runs(self, mock_fix):
        """Test the task simply calls the helper function for each given Run ID."""
        run_ids = [1, 2, 3]
        expected_calls = [call(run_id) for run_id in run_ids]
        calculation.fix_problematic_runs.run(run_ids)
        mock_fix.assert_has_calls(expected_calls)


class FixProblematicRunTest(TestCase):
    """Test case for helper function _fix_problematic_run."""

    def setUp(self):
        """
        Set up common variables for tests.

        For one user an account, crate events that should define two running periods of
        one hour each separated by one hour.
        """
        one_hour = datetime.timedelta(hours=1)
        account_setup_time = util_helper.utc_dt(2021, 6, 1, 0, 0, 0)
        power_on_time_a = account_setup_time + one_hour
        power_off_time_a = power_on_time_a + one_hour
        power_on_time_b = power_off_time_a + one_hour
        power_off_time_b = power_on_time_b + one_hour
        powered_times = (
            (power_on_time_a, power_off_time_a),
            (power_on_time_b, power_off_time_b),
        )
        with util_helper.clouditardis(account_setup_time):
            self.user = util_helper.generate_test_user()
            account = api_helper.generate_cloud_account(user=self.user)
            instance = api_helper.generate_instance(account)
            events = api_helper.generate_instance_events(instance, powered_times)

        api_helper.recalculate_runs_from_events(events)

        runs = models.Run.objects.all().order_by("id")
        self.assertEqual(len(runs), 2)

        self.okay_run = runs[0]
        # Force the second run into a problematic state.
        self.problematic_run = runs[1]
        self.problematic_run.end_time = None
        self.problematic_run.save()

    @patch("api.tasks.calculation.recalculate_runs")
    def test_run_not_found_does_nothing(self, mock_recalculate):
        """Test early return when the run is not found."""
        with self.assertLogs("api.tasks.calculation", level="INFO") as logging_watcher:
            calculation._fix_problematic_run(-1)
        self.assertIn("does not exist", logging_watcher.output[0])
        mock_recalculate.assert_not_called()

    @patch("api.tasks.calculation.recalculate_runs")
    def test_run_found_but_no_power_off_event_does_nothing(self, mock_recalculate):
        """Test early return when the run is found but no power_off event is found."""
        # Start by deleting the power_off event that would be for this run.
        # This means the supposedly problematic run is actually okay.
        models.InstanceEvent.objects.filter(
            event_type=models.InstanceEvent.TYPE.power_off
        ).order_by("-occurred_at").first().delete()

        with self.assertLogs("api.tasks.calculation", level="INFO") as logging_watcher:
            calculation._fix_problematic_run(self.problematic_run.id)
        self.assertIn("No relevant InstanceEvent exists", logging_watcher.output[0])
        mock_recalculate.assert_not_called()

    @patch("api.tasks.calculation.recalculate_runs")
    def test_run_found_but_is_okay_does_nothing(self, mock_recalculate):
        """Test early return when the run is found but is okay."""
        with self.assertLogs("api.tasks.calculation", level="INFO") as logging_watcher:
            calculation._fix_problematic_run(self.okay_run.id)
        self.assertIn("does not appear to require fixing", logging_watcher.output[0])
        mock_recalculate.assert_not_called()

    @patch("api.tasks.calculation.recalculate_runs")
    def test_run_found_and_fixed(self, mock_recalculate):
        """Test attempting to fix when the run is found and should be fixed."""
        with self.assertLogs("api.tasks.calculation", level="INFO") as logging_watcher:
            calculation._fix_problematic_run(self.problematic_run.id)
        self.assertIn("Attempting to fix problematic runs", logging_watcher.output[0])
        last_power_off = (
            models.InstanceEvent.objects.filter(
                event_type=models.InstanceEvent.TYPE.power_off
            )
            .order_by("-occurred_at")
            .first()
        )
        mock_recalculate.assert_called_once_with(last_power_off)
