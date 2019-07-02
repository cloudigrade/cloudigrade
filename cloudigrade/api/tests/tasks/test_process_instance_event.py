"""Collection of tests for tasks.process_instance_event."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api import tasks
from api.models import InstanceEvent, Run
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class ProcessInstanceEventTest(TestCase):
    """Celery task 'process_instance_event' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = api_helper.generate_aws_account(
            aws_account_id=self.aws_account_id,
            user=self.user,
            created_at=util_helper.utc_dt(2017, 12, 1, 0, 0, 0),
        )
        api_helper.generate_aws_ec2_definitions()

    def test_process_instance_event_recalculate_runs(self):
        """
        Test that we recalculate runs when new instance events occur.

        Initial Runs (2,-):
            [ #------------]

        New power off event at (,13) results in the run being updated (2,13):
            [ ############ ]

        """
        instance = api_helper.generate_aws_instance(self.account)

        started_at = util_helper.utc_dt(2018, 1, 2, 0, 0, 0)

        start_event = api_helper.generate_single_aws_instance_event(
            instance,
            occurred_at=started_at,
            event_type=InstanceEvent.TYPE.power_on,
            no_instance_type=True,
        )
        tasks.process_instance_event(start_event)

        occurred_at = util_helper.utc_dt(2018, 1, 13, 0, 0, 0)

        instance_event = api_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_off,
            no_instance_type=True,
        )
        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(started_at, runs[0].start_time)
        self.assertEqual(occurred_at, runs[0].end_time)

    @patch('api.tasks.recalculate_runs')
    def test_process_instance_event_new_run(self, mock_recalculate_runs):
        """
        Test new run is created if it occurred after all runs and is power on.

        account.util.recalculate_runs should not be ran in this case.

        Initial Runs (2,5):
            [ ####          ]

        New power on event at (10,) results in 2 runs (2,5) (10,-):
            [ ####    #-----]

        """
        instance = api_helper.generate_aws_instance(self.account)

        run_time = (
            util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
            util_helper.utc_dt(2018, 1, 5, 0, 0, 0),
        )

        api_helper.generate_single_run(instance, run_time)

        occurred_at = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
        instance_event = api_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=None,
        )
        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(2, len(runs))

        # Since we're adding a new run, recalculate_runs shouldn't be called
        mock_recalculate_runs.assert_not_called()

    def test_process_instance_event_duplicate_start(self):
        """
        Test that recalculate works when a duplicate start event is introduced.

        Initial Runs (5,7):
            [    ###        ]

        New power on event at (1,) results in the run being updated:
            [#######        ]

        New power on event at (3,) results in the run not being updated:
            [#######        ]

        """
        instance_type = 't1.potato'

        instance = api_helper.generate_aws_instance(self.account)

        run_time = [
            (
                util_helper.utc_dt(2018, 1, 5, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 7, 0, 0, 0),
            )
        ]

        instance_events = api_helper.generate_aws_instance_events(
            instance, run_time, instance_type=instance_type
        )
        api_helper.recalculate_runs_from_events(instance_events)

        first_start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)

        instance_event = api_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=first_start,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=instance_type,
        )

        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(run_time[0][1], runs[0].end_time)
        self.assertEqual(first_start, runs[0].start_time)

        second_start = util_helper.utc_dt(2018, 1, 3, 0, 0, 0)

        duplicate_start_event = api_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=second_start,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=instance_type,
        )

        tasks.process_instance_event(duplicate_start_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))
        self.assertEqual(run_time[0][1], runs[0].end_time)
        self.assertEqual(first_start, runs[0].start_time)

    @patch('api.tasks.recalculate_runs')
    def test_process_instance_event_power_off(self, mock_recalculate_runs):
        """
        Test new run is not if a power off event occurs after all runs.

        account.util.recalculate_runs should not be ran in this case.

        Initial Runs (2,5):
            [ ####          ]

        New power off event at (10,) results in 1 runs (2,5):
            [ ####          ]

        """
        instance = api_helper.generate_aws_instance(self.account)

        run_time = (
            util_helper.utc_dt(2018, 1, 2, 0, 0, 0),
            util_helper.utc_dt(2018, 1, 5, 0, 0, 0),
        )

        api_helper.generate_single_run(instance, run_time)

        occurred_at = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)

        instance_event = api_helper.generate_single_aws_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_off,
            instance_type=None,
        )
        tasks.process_instance_event(instance_event)

        runs = list(Run.objects.all())
        self.assertEqual(1, len(runs))

        mock_recalculate_runs.assert_not_called()
