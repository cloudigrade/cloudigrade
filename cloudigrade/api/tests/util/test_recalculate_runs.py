"""Collection of tests for util.recalculate_runs."""
import datetime
from unittest.mock import patch

from django.db.models import F
from django.db.models.functions import Coalesce
from django.test import TestCase

from api import models, util
from api.tests import helper as api_helper
from util.misc import get_today
from util.tests import helper as util_helper


class RecalculateRunsDataSetUpMixin:
    """Data helper mixin for related test classes."""

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
        Create various events and runs to exist before recalculating runs.

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

        # Important note: We want to backdate the created_at and modified_at values for
        # the InstanceEvents and Runs because they were set to the real "now" upon their
        # creation. This is necessary because we look at these datetimes when we
        # determine if a particular InstanceEvent requires a Run to be recalculated.
        models.InstanceEvent.objects.update(
            created_at=F("occurred_at"), updated_at=F("occurred_at")
        )
        # Nudge the times for the Runs slightly forward, though, so that when comparing
        # datetimes it's clear that the Runs were created slightly more recently.
        models.Run.objects.update(
            created_at=Coalesce(F("end_time"), F("start_time"))
            + datetime.timedelta(minutes=1),
            updated_at=Coalesce(F("end_time"), F("start_time"))
            + datetime.timedelta(minutes=1),
        )
        for event in events:
            event.refresh_from_db()
        for run in runs:
            run.refresh_from_db()

        return events, runs


class RecalculateRunsTest(RecalculateRunsDataSetUpMixin, TestCase):
    """Utility function 'recalculate_runs' test cases."""

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


class RecalculateRunsForInstanceIdTest(RecalculateRunsDataSetUpMixin, TestCase):
    """Utility function 'recalculate_runs_for_instance_id' test cases."""

    def test_recalculate_runs_because_no_runs_exist(self):
        """Test recalculating because no other Runs exist."""
        start_time = self.account_setup_time + self.one_hour
        event_power_times = ((start_time, None),)
        events, __ = self.preload_data(event_power_times, ())

        with patch.object(util, "recalculate_runs") as mock_recalc:
            util.recalculate_runs_for_instance_id(self.instance.id)
            mock_recalc.assert_called_once_with(events[0])

    def test_recalculate_runs_because_event_newer_than_run_exists(self):
        """Test recalculating because the InstanceEvent is newer than the newest Run."""
        start_time = self.account_setup_time + self.one_hour
        end_time = start_time + self.one_hour
        event_power_times = ((start_time, end_time),)
        run_times = ((start_time, None),)
        events, __ = self.preload_data(event_power_times, run_times)

        with patch.object(util, "recalculate_runs") as mock_recalc:
            util.recalculate_runs_for_instance_id(self.instance.id)
            mock_recalc.assert_called_once_with(events[1])

    def test_no_recalculate_runs_because_no_need(self):
        """Test not recalculating because no newer InstanceEvent exists."""
        start_time = self.account_setup_time + self.one_hour
        end_time = start_time + self.one_hour
        event_power_times = ((start_time, end_time),)
        run_times = ((start_time, end_time),)
        self.preload_data(event_power_times, run_times)

        with patch.object(util, "recalculate_runs") as mock_recalc:
            util.recalculate_runs_for_instance_id(self.instance.id)
            mock_recalc.assert_not_called()


class RecalculateRunsForCloudAccountIdTest(RecalculateRunsDataSetUpMixin, TestCase):
    """Utility function 'recalculate_runs_for_cloud_account_id' test cases."""

    def test_find_instance_that_needs_recalculated_runs(self):
        """Test finding an instance that needs recalculated runs."""
        start_time = self.account_setup_time + self.one_hour
        event_power_times = ((start_time, None),)
        self.preload_data(event_power_times, ())

        with patch.object(util, "recalculate_runs_for_instance_id") as mock_recalc:
            util.recalculate_runs_for_cloud_account_id(self.account.id)
            mock_recalc.assert_called_once_with(self.instance.id)

    def test_no_instances_because_too_recent_since(self):
        """
        Test not finding instances with a custom "since" time that's too recent.

        In this case, we deliberately choose a "since" time more recent than the last
        and only event. Because this excludes the event from being found, there appears
        to be no need to recalculate runs.
        """
        start_time = self.account_setup_time + self.one_hour
        event_power_times = ((start_time, None),)
        self.preload_data(event_power_times, ())

        since = start_time + self.one_hour
        with patch.object(util, "recalculate_runs_for_instance_id") as mock_recalc:
            util.recalculate_runs_for_cloud_account_id(self.account.id, since)
            mock_recalc.assert_not_called()
