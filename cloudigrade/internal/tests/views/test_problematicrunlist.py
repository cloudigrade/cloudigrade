"""Collection of tests for ProblematicRunList."""
import datetime
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from api import models
from api.tests import helper as api_helper
from internal import views
from util.tests import helper as util_helper


class ProblematicRunListTest(TestCase):
    """ProblematicRunList view test case."""

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
            self.events = api_helper.generate_instance_events(instance, powered_times)
        self.factory = APIRequestFactory()

    def generate_runs(self, problematic=False):
        """Generate the run for the test, optionally problematic."""
        events = self.events[:1] if problematic else self.events
        with patch("api.util.schedule_concurrent_calculation_task"):
            api_helper.recalculate_runs_from_events(events)
        expected_count = 1 if problematic else 2
        self.assertEqual(models.Run.objects.count(), expected_count)

    def api_call(self, method, args):
        """Make a dummy request to the problematic runs API."""
        func = getattr(self.factory, method)
        request = func("/dummy/path", args)
        view = views.ProblematicRunList.as_view()
        response = view(request)
        return response

    def api_get(self, args=None):
        """Make a dummy get request to the problematic runs API."""
        return self.api_call("get", args)

    def api_post(self, args=None):
        """Make a dummy post request to the problematic runs API."""
        return self.api_call("post", args)

    def assertResponseOkayFoundCount(self, response, count):
        """Assert the response has status 200 OK with expected count of Runs."""
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), count)

    def assertResponseAccepted(self, response):
        """Assert the response has status 202 Accepted."""
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def assertTaskCalledWithProblematicRun(self, mock_fix_task):
        """Assert the task was called with the problematic Run."""
        expected_run_id = models.Run.objects.first().id  # since there's only one run
        mock_fix_task.delay.assert_called_once_with([expected_run_id])

    def test_list_any_user_good_run_empty(self):
        """Test list with good runs returns nothing."""
        self.generate_runs(problematic=False)
        response = self.api_get()
        self.assertResponseOkayFoundCount(response, 0)

    def test_list_any_user_bad_run_found(self):
        """Test list with a bad run returns it."""
        self.generate_runs(problematic=True)
        response = self.api_get()
        self.assertResponseOkayFoundCount(response, 1)

    def test_list_specific_user_bad_run_found(self):
        """Test list for a specific user with a bad run returns it."""
        self.generate_runs(problematic=True)
        response = self.api_get({"user_id": self.user.id})
        self.assertResponseOkayFoundCount(response, 1)

    def test_list_other_user_bad_run_empty(self):
        """Test list for some other user (not having the bad run) returns nothing."""
        self.generate_runs(problematic=True)
        response = self.api_get({"user_id": self.user.id + 1})
        self.assertResponseOkayFoundCount(response, 0)

    @patch("api.tasks.fix_problematic_runs")
    def test_fix_any_user_bad_run_calls_task(self, mock_fix_task):
        """Test fixing bad runs with no user specified calls the fix task."""
        self.generate_runs(problematic=True)
        response = self.api_post()
        self.assertResponseAccepted(response)
        self.assertTaskCalledWithProblematicRun(mock_fix_task)

    @patch("api.tasks.fix_problematic_runs")
    def test_fix_specific_user_bad_run_calls_task(self, mock_fix_task):
        """Test fixing bad runs with a specific user calls the fix task."""
        self.generate_runs(problematic=True)
        response = self.api_post({"user_id": self.user.id})
        self.assertResponseAccepted(response)
        self.assertTaskCalledWithProblematicRun(mock_fix_task)

    @patch("api.tasks.fix_problematic_runs")
    def test_fix_for_other_user_does_nothing(self, mock_fix_task):
        """Test trying to fix runs for a user without bad runs does nothing."""
        self.generate_runs(problematic=True)
        response = self.api_post({"user_id": self.user.id + 1})
        self.assertResponseAccepted(response)
        mock_fix_task.assert_not_called()

    @patch("api.tasks.fix_problematic_runs")
    def test_fix_but_no_bad_runs_does_nothing(self, mock_fix_task):
        """Test trying to fix when there's nothing to fix does nothing."""
        self.generate_runs(problematic=False)
        response = self.api_post()
        self.assertResponseAccepted(response)
        mock_fix_task.assert_not_called()
