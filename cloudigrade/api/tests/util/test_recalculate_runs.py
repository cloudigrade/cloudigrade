"""Collection of tests for util.recalculate_runs."""
import datetime

from django.test import TestCase

from api import models, util
from api.tests import helper as api_helper
from util.misc import get_today
from util.tests import helper as util_helper


class RecalculateRunsTest(TestCase):
    """Utility function 'recalculate_runs' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        today = get_today()
        self.one_hour = datetime.timedelta(hours=1)
        self.account_setup_time = util_helper.utc_dt(today.year, today.month, today.day)
        with util_helper.clouditardis(self.account_setup_time):
            self.user = util_helper.generate_test_user()
            self.account = api_helper.generate_cloud_account(user=self.user)
            self.instance = api_helper.generate_instance(self.account)
            self.machine_image = self.instance.machine_image

    def preload_data(self, event_powered_times, run_times):
        """
        Create various events and runs to exist before running recalculate_runs.

        Args:
            event_powered_times (iterable): iterable of tuples each containing the
                start and stop times for InstanceEvent objects to create
            run_times (iterable): iterable of tuples each containing the
                start and stop times for Run objects to create

        Returns:
            tuple[list, list] containing the created InstanceEvent and Run objects.
        """
        events = api_helper.generate_instance_events(
            self.instance,
            event_powered_times,
            self.machine_image.content_object.ec2_ami_id,
        )
        runs = []
        for run_time in run_times:
            start_time, end_time = run_time
            run = models.Run.objects.create(
                start_time=start_time,
                end_time=end_time,
                instance=self.instance,
                machineimage=self.machine_image,
            )
            runs.append(run)
        return events, runs

    def assertExpectedRuns(self, old_runs, expected_run_times, recreated=True):
        """
        Assert the newly created runs have the expected run times.

        Args:
            old_runs (iterable): the Run objects that existed before recalculating runs
            expected_run_times (iterable): iterable of tuples each containing the
                expected start and stop times of all current Run objects
            recreated (bool): optional should the old runs have been recreated
        """
        new_runs = models.Run.objects.order_by("start_time")
        self.assertEqual(len(new_runs), len(expected_run_times))
        for index, old_run in enumerate(old_runs):
            if recreated:
                with self.assertRaises(models.Run.DoesNotExist):
                    old_run.refresh_from_db()
            else:
                old_run.refresh_from_db()
                self.assertEqual(old_run, new_runs[index])

        for index, new_run in enumerate(new_runs):
            expected_start_time, expected_end_time = expected_run_times[index]
            self.assertEqual(new_run.start_time, expected_start_time)
            self.assertEqual(new_run.end_time, expected_end_time)

    def test_power_on_creates_run(self):
        """Test most basic case with one power_on event and no existing runs."""
        start_time = self.account_setup_time + self.one_hour
        event_power_times = ((start_time, None),)
        old_run_times = ()
        events, old_runs = self.preload_data(event_power_times, old_run_times)

        # recalculate from the first (and only) event
        util.recalculate_runs(events[0])

        expected_run_times = event_power_times
        self.assertExpectedRuns(old_runs, expected_run_times)

    def test_power_off_recreates_existing_run(self):
        """Test case with an existing run that doesn't yet account for the power_off."""
        start_time = self.account_setup_time + self.one_hour
        end_time = start_time + self.one_hour
        event_power_times = ((start_time, end_time),)
        old_run_times = ((start_time, None),)
        events, old_runs = self.preload_data(event_power_times, old_run_times)

        # recalculate from the power_off event
        util.recalculate_runs(events[1])

        expected_run_times = event_power_times
        self.assertExpectedRuns(old_runs, expected_run_times)

    def test_backdated_power_off_recreates_runs(self):
        """
        Test handling an out-of-order or back-dated power_off event.

        Consider the case where we receive events in the order [on, on, off] and receive
        an "off" out of order that was supposed to occur between the two "on" events.
        Before handling the out-of-order "off", we would have one long run from the time
        of the first "on" to the time of the (then only) "off". Upon receiving the final
        out-of-order "off", recalculation should result in two runs since the sequence
        of events has become [on, off, on off].
        """
        first_start_time = self.account_setup_time + self.one_hour
        first_end_time = first_start_time + self.one_hour
        second_start_time = first_end_time + self.one_hour
        second_end_time = second_start_time + self.one_hour

        event_power_times = (
            (first_start_time, first_end_time),
            (second_start_time, second_end_time),
        )
        old_run_times = ((first_start_time, second_end_time),)
        events, old_runs = self.preload_data(event_power_times, old_run_times)

        # recalculate from the backdated but chronologically first power_off event
        util.recalculate_runs(events[1])

        expected_run_times = event_power_times
        self.assertExpectedRuns(old_runs, expected_run_times)

    def test_early_return_when_no_change_needed(self):
        """Test recalculate_runs returns early when no changes are needed."""
        first_start_time = self.account_setup_time + self.one_hour
        first_end_time = first_start_time + self.one_hour
        second_start_time = first_end_time + self.one_hour
        second_end_time = second_start_time + self.one_hour

        event_power_times = (
            (first_start_time, first_end_time),
            (second_start_time, second_end_time),
        )
        old_run_times = ()
        events, old_runs = self.preload_data(event_power_times, old_run_times)

        # calculate once to set the data up.
        first_created_runs = util.recalculate_runs(events[0])
        self.assertEqual(len(first_created_runs), 2)
        self.assertExpectedRuns(old_runs, event_power_times)

        # calculate a second time for this test case.
        second_created_runs = util.recalculate_runs(events[0])
        self.assertEqual(len(second_created_runs), 0)
        self.assertExpectedRuns(old_runs, event_power_times, recreated=False)
