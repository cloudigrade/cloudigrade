"""Collection of tests for AccountViewSet."""
import datetime

from django.utils.translation import gettext as _
from rest_framework.test import APIClient

from api.tests import helper as api_helper
from api.tests.views.shared.test_dailyconcurrentusageviewset import (
    SharedDailyConcurrentUsageViewSetTest,
)
from util.misc import get_today


class InternalDailyConcurrentUsageViewSetTest(SharedDailyConcurrentUsageViewSetTest):
    """InternalDailyConcurrentUsageViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        super().setUp(concurrent_api_url="/internal/api/cloudigrade/v1/concurrent/")

    def test_future_start_date_returns_400(self):
        """
        Test with far-future start_date, expecting it to return 400.

        When an start_date is given that is tomorrow or later, we return
        a 400 response, because we cannot predict the future.
        """
        today = get_today()
        future = today + datetime.timedelta(days=1)
        data = {"start_date": str(future)}
        api_helper.calculate_concurrent(today, future, self.user1.id)

        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        self.assertEqual(response.status_code, 400)

        body = response.json()
        self.assertEqual(body["start_date"], [_("start_date cannot be in the future.")])

    def test_future_start_and_end_date_returns_400(self):
        """
        Test with far-future start_date and end_date, expecting no results.

        If the request filters result in dates that are only in the future, we must
        always expect a 400 response because we cannot possibly know
        anything beyond today.
        """
        today = get_today()
        future_start = today + datetime.timedelta(days=50)
        future_end = today + datetime.timedelta(days=100)
        data = {"start_date": str(future_start), "end_date": str(future_end)}
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        self.assertEqual(response.status_code, 400)

        body = response.json()
        self.assertEqual(body["start_date"], [_("start_date cannot be in the future.")])
        self.assertEqual(body["end_date"], [_("end_date cannot be in the future.")])
