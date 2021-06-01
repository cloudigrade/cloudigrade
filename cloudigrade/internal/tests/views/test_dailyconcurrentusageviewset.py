"""Collection of tests for AccountViewSet."""
import datetime

import faker
from django.utils.translation import gettext as _
from rest_framework.test import APIClient

from api.tests import helper as api_helper
from api.tests.views.shared.test_dailyconcurrentusageviewset import (
    SharedDailyConcurrentUsageViewSetTest,
)
from util.misc import get_today
from util.tests import helper as util_helper

_faker = faker.Faker()


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

    def test_valid_account_number_and_org_admin_headers_defaults(self):
        """
        Test with valid account_number and org_admin returns defaults.

        Test with an internal account header, valid account_number and True
        org_admin headers, expect a normal response for the default start_date
        of "yesterday".
        """
        yesterday = get_today() - datetime.timedelta(days=1)
        today = get_today()
        api_helper.calculate_concurrent(yesterday, today, self.user1.id)

        client = APIClient()
        client.credentials(
            HTTP_X_RH_IDENTITY=util_helper.get_internal_identity_auth_header(),
            HTTP_X_RH_IDENTITY_ACCOUNT=self.user1.username,
            HTTP_X_RH_IDENTITY_ORG_ADMIN="True",
        )
        response = client.get(self.concurrent_api_url, data={}, format="json")
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["date"], str(yesterday))

    def test_invalid_account_number_parameter(self):
        """
        Test with an invalid account_number parameter.

        Test with an internal account header, an invalid account_number and True
        org_admin headers, expect an authentication error.
        """
        yesterday = get_today() - datetime.timedelta(days=1)
        today = get_today()
        invalid_account_number = str(_faker.pyint())
        api_helper.calculate_concurrent(yesterday, today, self.user1.id)

        client = APIClient()
        client.credentials(
            HTTP_X_RH_IDENTITY=util_helper.get_internal_identity_auth_header(),
            HTTP_X_RH_IDENTITY_ACCOUNT=invalid_account_number,
            HTTP_X_RH_IDENTITY_ORG_ADMIN="True",
        )
        response = client.get(self.concurrent_api_url, data={}, format="json")
        body = response.json()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["detail"], "Incorrect authentication credentials.")

    def test_with_false_is_org_admin_parameter(self):
        """
        Test with a False is_org_admin parameter.

        Test with an internal account header, a valid account_number and False
        org_admin headers, expect an authentication error.
        """
        yesterday = get_today() - datetime.timedelta(days=1)
        today = get_today()
        api_helper.calculate_concurrent(yesterday, today, self.user1.id)

        client = APIClient()
        client.credentials(
            HTTP_X_RH_IDENTITY=util_helper.get_internal_identity_auth_header(),
            HTTP_X_RH_IDENTITY_ACCOUNT=self.user1.username,
            HTTP_X_RH_IDENTITY_ORG_ADMIN="False",
        )
        response = client.get(self.concurrent_api_url, data={}, format="json")
        body = response.json()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(body["detail"], "User must be an org admin.")
