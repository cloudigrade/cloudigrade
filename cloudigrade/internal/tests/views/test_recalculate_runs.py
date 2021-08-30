"""Collection of tests for the internal recalculate_runs view."""
import datetime
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from api.tests import helper as api_helper
from internal.views import recalculate_runs
from util.tests import helper as util_helper


class RecalculateRunsViewTest(TestCase):
    """Internal recalculate_runs view test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.factory = APIRequestFactory()
        date_joined = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.user = util_helper.generate_test_user(date_joined=date_joined)
        self.account = api_helper.generate_cloud_account(
            user=self.user, created_at=date_joined
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.calculation._recalculate_runs_for_cloud_account_id")
    def test_recalculate_runs_no_args(self, mock_recalculate):
        """Assert recalculate task triggered with no args."""
        request = self.factory.post("/recalculate_runs/", data={}, format="json")
        response = recalculate_runs(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(self.account.id, None)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.calculation._recalculate_runs_for_cloud_account_id")
    def test_recalculate_runs_cloud_account_id(self, mock_recalculate):
        """Assert recalculate task triggered with valid cloud_account_id."""
        request = self.factory.post(
            "/recalculate_runs/", data={"cloud_account_id": "420"}, format="json"
        )
        response = recalculate_runs(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(420, None)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.calculation._recalculate_runs_for_cloud_account_id")
    def test_recalculate_runs_bad_cloud_account_id(self, mock_recalculate):
        """Assert recalculate task not triggered with malformed cloud_account_id."""
        request = self.factory.post(
            "/recalculate_runs/", data={"cloud_account_id": "potato"}, format="json"
        )
        response = recalculate_runs(request)
        self.assertEqual(response.status_code, 400)
        mock_recalculate.assert_not_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.calculation._recalculate_runs_for_cloud_account_id")
    def test_recalculate_runs_since(self, mock_recalculate):
        """Assert recalculate task triggered with valid since date."""
        request = self.factory.post(
            "/recalculate_runs/", data={"since": "2021-06-09"}, format="json"
        )
        expected_since = util_helper.utc_dt(2021, 6, 9)
        response = recalculate_runs(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(self.account.id, expected_since)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.calculation._recalculate_runs_for_cloud_account_id")
    def test_recalculate_runs_since_with_timezone(self, mock_recalculate):
        """Assert recalculate task triggered with valid since datetime+offset."""
        request = self.factory.post(
            "/recalculate_runs/",
            data={"since": "2021-06-09 04:02:00+04"},
            format="json",
        )
        expected_since = datetime.datetime(
            2021, 6, 9, 4, 2, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=4))
        )
        response = recalculate_runs(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(self.account.id, expected_since)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.calculation._recalculate_runs_for_cloud_account_id")
    def test_recalculate_runs_bad_since(self, mock_recalculate):
        """Assert recalculate task not triggered with malformed since."""
        request = self.factory.post(
            "/recalculate_runs/", data={"since": "potato"}, format="json"
        )
        response = recalculate_runs(request)
        self.assertEqual(response.status_code, 400)
        mock_recalculate.assert_not_called()
