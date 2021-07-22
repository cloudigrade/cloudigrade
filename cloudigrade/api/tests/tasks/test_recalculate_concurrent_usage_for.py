"""Collection of tests for tasks.recalculate_concurrent_usage_for_* functions."""
import datetime
from unittest.mock import Mock, call, patch

import faker
from dateutil.rrule import DAILY, rrule
from django.test import TestCase

from api import models, tasks, util
from api.tests import helper as api_helper
from util.misc import get_today
from util.tests import helper as util_helper

_faker = faker.Faker()


class RecalculateConcurrentUsageForAllUsersTest(TestCase):
    """Async function 'recalculate_concurrent_usage_for_all_users` test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.users = [
            util_helper.generate_test_user(),
            util_helper.generate_test_user(),
        ]

    @patch("api.tasks.recalculate_concurrent_usage_for_user_id")
    def test_recalculate_usage_for_all(self, mock_recalculate_for_user):
        """Test typical behavior triggers recalculation for all users."""
        tasks.recalculate_concurrent_usage_for_all_users()

        expected_calls = [
            call(args=(user.id, None), serializer="pickle") for user in self.users
        ]
        mock_recalculate_for_user.apply_async.assert_has_calls(expected_calls)

    @patch("api.tasks.recalculate_concurrent_usage_for_user_id")
    def test_recalculate_usage_for_all_since(self, mock_recalculate_for_user):
        """Test typical behavior triggers recalculation for all users since a date."""
        since = Mock()

        tasks.recalculate_concurrent_usage_for_all_users(since)

        expected_calls = [
            call(args=(user.id, since), serializer="pickle") for user in self.users
        ]
        mock_recalculate_for_user.apply_async.assert_has_calls(expected_calls)


class RecalculateConcurrentUsageForUserIdTask(TestCase):
    """Async function 'recalculate_concurrent_usage_for_user_id` test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user(
            date_joined=util_helper.utc_dt(2021, 4, 1)
        )

    @util_helper.clouditardis(util_helper.utc_dt(2021, 6, 20, 0, 0, 0))
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id_on_date")
    def test_recalculate_usage_for_user(self, mock_recalculate_for_user_on_date):
        """Test typical behavior triggers recalculation for user since default date."""
        tasks.recalculate_concurrent_usage_for_user_id(self.user.id)

        since_days_ago = 7  # TODO change if this default value becomes configurable
        today = get_today()
        default_since = today - datetime.timedelta(days=since_days_ago)
        expected_dates = [
            _datetime.date()
            for _datetime in rrule(freq=DAILY, dtstart=default_since, until=today)
        ]
        expected_calls = [
            call(args=(self.user.id, date), serializer="pickle")
            for date in expected_dates
        ]
        mock_recalculate_for_user_on_date.apply_async.assert_has_calls(expected_calls)

    @util_helper.clouditardis(util_helper.utc_dt(2021, 6, 20, 0, 0, 0))
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id_on_date")
    def test_recalculate_usage_for_user_since(self, mock_recalculate_for_user_on_date):
        """Test typical behavior triggers recalculation for user since given date."""
        today = get_today()
        since_days_ago = _faker.random_int(min=10, max=30)
        since = today - datetime.timedelta(days=since_days_ago)

        tasks.recalculate_concurrent_usage_for_user_id(self.user.id, since)

        expected_dates = [
            _datetime.date()
            for _datetime in rrule(freq=DAILY, dtstart=since, until=today)
        ]
        expected_calls = [
            call(args=(self.user.id, date), serializer="pickle")
            for date in expected_dates
        ]
        mock_recalculate_for_user_on_date.apply_async.assert_has_calls(expected_calls)


class RecalculateConcurrentUsageForUserIdOnDateTest(TestCase):
    """Async function 'recalculate_concurrent_usage_for_user_id_on_date` test cases."""

    def setUp(self):
        """
        Set up common variables for tests.

        This defines one user with with cloud account with one instance.
        The instance has events to power on, off, on, and off again.
        Two runs are created correctly covering those four events.
        """
        one_hour = datetime.timedelta(hours=1)
        self.account_setup_time = util_helper.utc_dt(2021, 6, 1, 0, 0, 0)
        power_on_time_a = self.account_setup_time + one_hour
        power_off_time_a = power_on_time_a + one_hour
        power_on_time_b = power_off_time_a + one_hour
        power_off_time_b = power_on_time_b + one_hour
        powered_times = (
            (power_on_time_a, power_off_time_a),
            (power_on_time_b, power_off_time_b),
        )
        self.user = util_helper.generate_test_user(date_joined=self.account_setup_time)
        self.account = api_helper.generate_cloud_account(
            user=self.user, created_at=self.account_setup_time
        )
        self.instance = api_helper.generate_instance(self.account)
        self.events = api_helper.generate_instance_events(self.instance, powered_times)
        self.runs = util.recalculate_runs(self.events[0])

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_usage_does_not_exist_needs_calculation(self, mock_calculate):
        """Test calculating because ConcurrentUsage does not yet exist."""
        target_date = self.account_setup_time.date()
        tasks.recalculate_concurrent_usage_for_user_id_on_date(
            self.user.id, target_date
        )
        mock_calculate.assert_called_with(target_date, self.user.id)

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_usage_exists_but_different_runs_needs_calculation(self, mock_calculate):
        """Test calculating because ConcurrentUsage exists without expected runs."""
        target_date = self.account_setup_time.date()

        # Create a bogus ConcurrentUsage object that needs recalculation.
        concurrent_usage = models.ConcurrentUsage.objects.create(
            date=target_date, user=self.user
        )
        # Since this does not contain *all* the relevant runs, it should recalculate.
        concurrent_usage.potentially_related_runs.add(self.runs[0])
        concurrent_usage.save()

        tasks.recalculate_concurrent_usage_for_user_id_on_date(
            self.user.id, target_date
        )
        mock_calculate.assert_called_with(target_date, self.user.id)

    @patch("api.tasks.calculate_max_concurrent_usage")
    def test_usage_exists_with_same_runs_no_calculation(self, mock_calculate):
        """Test not calculating because ConcurrentUsage exists with expected runs."""
        target_date = self.account_setup_time.date()

        concurrent_usage = models.ConcurrentUsage.objects.create(
            date=target_date, user=self.user
        )
        # Since this contains *all* the relevant runs, it should *not* recalculate.
        concurrent_usage.potentially_related_runs.add(*self.runs)
        concurrent_usage.save()

        tasks.recalculate_concurrent_usage_for_user_id_on_date(
            self.user.id, target_date
        )
        mock_calculate.assert_not_called()
