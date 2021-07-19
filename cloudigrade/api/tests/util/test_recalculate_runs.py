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

    def test_power_on_creates_run(self):
        """Test most basic case with one power_on event."""
        start_time = self.account_setup_time + self.one_hour
        event = api_helper.generate_single_instance_event(
            instance=self.instance,
            occurred_at=start_time,
            event_type=models.InstanceEvent.TYPE.power_on,
        )

        util.recalculate_runs(event)

        # Expect the run's start time to match but to have no end time.
        run = models.Run.objects.get()
        self.assertEqual(run.start_time, start_time)
        self.assertIsNone(run.end_time)

    def test_power_off_recreates_existing_run(self):
        """Test case with power_on event after run exists."""
        start_time = self.account_setup_time + self.one_hour
        end_time = start_time + self.one_hour
        __, event_off = api_helper.generate_instance_events(
            self.instance, [(start_time, end_time)]
        )
        run = models.Run.objects.create(start_time=start_time, instance=self.instance)

        util.recalculate_runs(event_off)

        with self.assertRaises(models.Run.DoesNotExist):
            # Expect the original run was destroyed to be recreated.
            # To ease calculations, we trash all related runs from a point in time and
            # rebuild all anew from that point forward.
            run.refresh_from_db()

        # Expect the run's start and end times to match.
        run = models.Run.objects.get()
        self.assertEqual(run.start_time, start_time)
        self.assertEqual(run.end_time, end_time)

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
        events = api_helper.generate_instance_events(
            self.instance,
            [(first_start_time, first_end_time), (second_start_time, second_end_time)],
        )
        first_on, first_off, second_on, second_off = events

        # Set up the initial Run that we expect to be deleted and recreated into two.
        run = models.Run.objects.create(
            start_time=first_start_time,
            end_time=second_end_time,
            instance=self.instance,
        )

        util.recalculate_runs(first_off)

        with self.assertRaises(models.Run.DoesNotExist):
            # Expect the original run was destroyed to be recreated.
            run.refresh_from_db()

        self.assertEqual(models.Run.objects.count(), 2)
        first_run, second_run = models.Run.objects.order_by("start_time")
        self.assertEqual(first_run.start_time, first_start_time)
        self.assertEqual(first_run.end_time, first_end_time)
        self.assertEqual(second_run.start_time, second_start_time)
        self.assertEqual(second_run.end_time, second_end_time)

    def test_early_return_when_no_change_needed(self):
        """Test recalculate_runs returns early when no changes are needed."""
        first_start_time = self.account_setup_time + self.one_hour
        first_end_time = first_start_time + self.one_hour
        second_start_time = first_end_time + self.one_hour
        second_end_time = second_start_time + self.one_hour
        events = api_helper.generate_instance_events(
            self.instance,
            [(first_start_time, first_end_time), (second_start_time, second_end_time)],
        )
        first_on = events[0]

        # calculate once to set the data up.
        first_created_runs = util.recalculate_runs(first_on)
        self.assertEqual(len(first_created_runs), 2)

        # calculate a second time for this test case.
        second_created_runs = util.recalculate_runs(first_on)
        self.assertEqual(len(second_created_runs), 0)
