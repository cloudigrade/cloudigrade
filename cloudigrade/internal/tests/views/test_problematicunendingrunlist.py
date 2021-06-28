"""Collection of tests for ProblematicUnendingRunList."""
import datetime
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory

from api.tests import helper as api_helper
from internal import views
from util.tests import helper as util_helper


class ProblematicUnendingRunListTest(TestCase):
    """ProblematicUnendingRunList view test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.account_setup_time = util_helper.utc_dt(2021, 6, 1, 0, 0, 0)
        self.power_on_time = self.account_setup_time + datetime.timedelta(hours=1)
        self.power_off_time = self.power_on_time + datetime.timedelta(hours=1)

        with util_helper.clouditardis(self.account_setup_time):
            self.user = util_helper.generate_test_user()
            self.account = api_helper.generate_cloud_account(user=self.user)
            self.instance = api_helper.generate_instance(self.account)

        self.events = api_helper.generate_instance_events(
            self.instance, [(self.power_on_time, self.power_off_time)]
        )

        self.factory = APIRequestFactory()

    def generate_run(self, problematic=False):
        """Generate the run for the test, optionally problematic."""
        events = self.events[:1] if problematic else self.events
        with patch("api.util.schedule_concurrent_calculation_task"):
            api_helper.recalculate_runs_from_events(events)

    def api_get(self, args=None):
        """Make a dummy get request to the problematic unending runs API."""
        request = self.factory.get("/dummy/path", args)
        view = views.ProblematicUnendingRunList.as_view()
        response = view(request)
        return response

    def api_post(self, args=None):
        """Make a dummy post request to the problematic unending runs API."""
        request = self.factory.post("/dummy/path", args)
        view = views.ProblematicUnendingRunList.as_view()
        response = view(request)
        return response

    def test_list_any_user_good_run_empty(self):
        """Test list with good run finds nothing."""
        self.generate_run(problematic=False)
        response = self.api_get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_specific_user_good_run_empty(self):
        """Test list with good run for specified user finds nothing."""
        self.generate_run(problematic=False)
        response = self.api_get({"user_id": self.user.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_list_any_user_bad_run_found(self):
        """Test list with bad run finds that run."""
        self.generate_run(problematic=True)
        response = self.api_get()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_specific_user_bad_run_found(self):
        """Test list with bad run for specified user finds that run."""
        self.generate_run(problematic=True)
        response = self.api_get({"user_id": self.user.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_list_other_user_bad_run_empty(self):
        """Test list with bad run for other user finds that nothing."""
        self.generate_run(problematic=True)
        response = self.api_get({"user_id": self.user.id + 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    @patch("api.tasks.process_instance_event")
    def test_fix_good_run_does_nothing(self, mock_process):
        """Test "fixing" a good run does nothing."""
        self.generate_run(problematic=False)
        response = self.api_post()
        mock_process.delay.assert_not_called()
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    @patch("api.tasks.process_instance_event")
    def test_fix_bad_run_any_user(self, mock_process):
        """Test fixing bad runs with no user specified calls the task."""
        self.generate_run(problematic=True)
        with self.assertLogs("internal.views", level="WARNING") as logging_watcher:
            response = self.api_post()
        mock_process.delay.assert_called()
        self.assertIn("Attempting to fix problematic", logging_watcher.output[0])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    @patch("api.tasks.process_instance_event")
    def test_fix_bad_run_specific_user(self, mock_process):
        """Test fixing bad runs with its user specified calls the task."""
        self.generate_run(problematic=True)
        with self.assertLogs("internal.views", level="WARNING") as logging_watcher:
            response = self.api_post({"user_id": self.user.id})
        mock_process.delay.assert_called()
        self.assertIn("Attempting to fix problematic", logging_watcher.output[0])
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    @patch("api.tasks.process_instance_event")
    def test_fix_bad_run_other_user_does_nothing(self, mock_process):
        """Test fixing bad runs with some other user specified does nothing."""
        self.generate_run(problematic=True)
        response = self.api_post({"user_id": self.user.id + 1})
        mock_process.delay.assert_not_called()
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
