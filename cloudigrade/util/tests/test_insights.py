"""Collection of tests for ``util.insights`` module."""
import http
import json
from unittest.mock import MagicMock, Mock, patch

import faker
from django.test import TestCase

from util import insights
from util.exceptions import SourcesAPINotJsonContent, SourcesAPINotOkStatus

_faker = faker.Faker()


class InsightsTest(TestCase):
    """Insights module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()

    def test_generate_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9u" "dW1iZXIiOiAiMTIzNDU2Nzg5MCJ9fQ=="
            )
        }
        actual = insights.generate_http_identity_headers(known_account_number)
        self.assertEqual(actual, expected)

    @patch("requests.get")
    def test_get_sources_authentication_success(self, mock_get):
        """Assert get_sources_authentication returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        authentication = insights.get_sources_authentication(
            self.account_number, self.authentication_id
        )
        self.assertEqual(authentication, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_fail_404(self, mock_get):
        """Assert get_sources_authentication fails when response is 404."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND
        with self.assertRaises(SourcesAPINotOkStatus):
            insights.get_sources_authentication(
                self.account_number, self.authentication_id
            )
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_fail_not_json(self, mock_get):
        """Assert get_sources_authentication fails when response isn't JSON."""
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.side_effect = json.decoder.JSONDecodeError(
            Mock(), MagicMock(), MagicMock()
        )
        with self.assertRaises(SourcesAPINotJsonContent):
            insights.get_sources_authentication(
                self.account_number, self.authentication_id
            )
        mock_get.assert_called()
