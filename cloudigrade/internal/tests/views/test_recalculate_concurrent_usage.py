"""Collection of tests for the internal recalculate_concurrent_usage view."""
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from internal.views import recalculate_concurrent_usage
from util.tests import helper as util_helper


class RecalculateConcurrentUsageViewTest(TestCase):
    """Internal recalculate_concurrent_usage view test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.factory = APIRequestFactory()
        date_joined = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.user = util_helper.generate_test_user(date_joined=date_joined)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id.apply_async")
    def test_recalculate_concurrent_usage_no_args(self, mock_recalculate):
        """Assert recalculate task triggered with no args."""
        request = self.factory.post(
            "/recalculate_concurrent_usage/", data={}, format="json"
        )
        response = recalculate_concurrent_usage(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(
            args=(self.user.id, None), serializer="pickle"
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id.apply_async")
    def test_recalculate_concurrent_usage_user_id(self, mock_recalculate):
        """Assert recalculate task triggered with valid user_id."""
        request = self.factory.post(
            "/recalculate_concurrent_usage/", data={"user_id": "420"}, format="json"
        )
        response = recalculate_concurrent_usage(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(args=(420, None), serializer="pickle")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id.apply_async")
    def test_recalculate_concurrent_usage_bad_user_id(self, mock_recalculate):
        """Assert recalculate task not triggered with malformed user_id."""
        bad_user_ids = ["potato", {"hello": "world"}, ["potato"]]
        for bad_user_id in bad_user_ids:
            request = self.factory.post(
                "/recalculate_concurrent_usage/",
                data={"user_id": bad_user_id},
                format="json",
            )
            response = recalculate_concurrent_usage(request)
            self.assertEqual(
                response.status_code,
                400,
                f"Unexpected non-400 status code '{response.status_code}' "
                f"for 'user_id' value '{bad_user_id}'",
            )
            mock_recalculate.assert_not_called()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id.apply_async")
    def test_recalculate_concurrent_usage_since(self, mock_recalculate):
        """Assert recalculate task triggered with valid since date."""
        request = self.factory.post(
            "/recalculate_concurrent_usage/",
            data={"since": "2021-06-09"},
            format="json",
        )
        expected_since = util_helper.utc_dt(2021, 6, 9).date()
        response = recalculate_concurrent_usage(request)
        self.assertEqual(response.status_code, 202)
        mock_recalculate.assert_called_with(
            args=(self.user.id, expected_since), serializer="pickle"
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("api.tasks.recalculate_concurrent_usage_for_user_id.apply_async")
    def test_recalculate_concurrent_usage_bad_since(self, mock_recalculate):
        """Assert recalculate task not triggered with malformed since."""
        bad_dates = ["potato", "yesterday", -1, {"hello": "world"}, ["potato"]]

        for bad_date in bad_dates:
            request = self.factory.post(
                "/recalculate_concurrent_usage/",
                data={"since": bad_date},
                format="json",
            )
            response = recalculate_concurrent_usage(request)
            self.assertEqual(
                response.status_code,
                400,
                f"Unexpected non-400 status code '{response.status_code}' "
                f"for 'since' value '{bad_date}'",
            )
            mock_recalculate.assert_not_called()
