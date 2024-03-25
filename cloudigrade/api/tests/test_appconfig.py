"""Collection of tests for application configuration, IPP12, etc."""

import http

from django.test import TestCase
from rest_framework.test import APIClient

from api.tests import helper as api_helper
from util.tests import helper as util_helper


class AppConfigSetTest(TestCase):
    """AppConfigSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()

        self.account1 = api_helper.generate_cloud_account(user=self.user1)
        self.account2 = api_helper.generate_cloud_account(user=self.user1)

    def test_pagination_links(self):
        """
        Test proper pagination links do not include duplicate application prefix.

        This test asserts that the pagination links returned do not include
        the duplicate /api/cloudigrade application prefix.
        """
        client = APIClient()
        client.force_authenticate(user=self.user1)
        data = {"limit": 1}
        response = client.get("/api/cloudigrade/v2/accounts/", data=data, format="json")
        body = response.json()

        self.assertEquals(body["meta"]["count"], 2)
        self.assertEquals(len(body["data"]), 1)

        link_first = body["links"]["first"]
        self.assertNotIn("/api/cloudigrade/api/cloudigrade", link_first)

        link_next = body["links"]["next"]
        self.assertNotIn("/api/cloudigrade/api/cloudigrade", link_next)

        link_last = body["links"]["last"]
        self.assertNotIn("/api/cloudigrade/api/cloudigrade", link_last)

    def test_valid_pagination_links(self):
        """
        Test that pagination links are reachable.

        This test asserts that the pagination links returned are
        properly configured and reachable.
        """
        client = APIClient()
        client.force_authenticate(user=self.user1)
        data = {"limit": 1}
        response = client.get("/api/cloudigrade/v2/accounts/", data=data, format="json")
        body = response.json()

        self.assertEquals(body["meta"]["count"], 2)
        self.assertEquals(len(body["data"]), 1)

        link_next = body["links"]["next"]
        response = client.get(link_next, data=data, format="json")
        body = response.json()

        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        self.assertEquals(len(body["data"]), 1)

    def test_internal_pagination_links(self):
        """
        Test proper internal links do not include duplicate application prefix.

        This test asserts that the pagination links returned do not include
        the duplicate /api/cloudigrade application prefix.
        """
        client = APIClient()
        client.force_authenticate(user=self.user1)
        data = {"limit": 1}
        response = client.get(
            "/internal/api/cloudigrade/v1/accounts/", data=data, format="json"
        )
        body = response.json()

        self.assertEquals(body["meta"]["count"], 2)
        self.assertEquals(len(body["data"]), 1)

        link_first = body["links"]["first"]
        self.assertNotIn("/api/cloudigrade/internal", link_first)

        link_next = body["links"]["next"]
        self.assertNotIn("/api/cloudigrade/internal", link_next)

        link_last = body["links"]["last"]
        self.assertNotIn("/api/cloudigrade/internal", link_last)

    def test_valid_internal_pagination_links(self):
        """
        Test that internal pagination links are reachable.

        This test asserts that the internal pagination links returned are
        properly configured and reachable.
        """
        client = APIClient()
        client.force_authenticate(user=self.user1)
        data = {"limit": 1}
        response = client.get(
            "/internal/api/cloudigrade/v1/accounts/", data=data, format="json"
        )
        body = response.json()

        self.assertEquals(body["meta"]["count"], 2)
        self.assertEquals(len(body["data"]), 1)

        link_next = body["links"]["next"]
        response = client.get(link_next, data=data, format="json")
        body = response.json()

        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        self.assertEquals(len(body["data"]), 1)
