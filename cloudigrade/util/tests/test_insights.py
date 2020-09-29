"""Collection of tests for ``util.insights`` module."""
import base64
import http
import json
from unittest.mock import MagicMock, Mock, patch

import faker
from django.test import TestCase, override_settings

from util import insights
from util.exceptions import SourcesAPINotJsonContent, SourcesAPINotOkStatus

_faker = faker.Faker()


class InsightsTest(TestCase):
    """Insights module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()
        self.application_id = _faker.pyint()

    def test_generate_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzNDU2Nzg5MCJ9fQ=="
            )
        }
        actual = insights.generate_http_identity_headers(known_account_number)
        self.assertEqual(actual, expected)

    def test_generate_org_admin_http_identity_headers(self):
        """Assert generation of an appropriate HTTP identity headers."""
        known_account_number = "1234567890"
        expected = {
            "X-RH-IDENTITY": (
                "eyJpZGVudGl0eSI6IHsiYWNjb3VudF9udW1iZXIiOiAiMTIzND"
                "U2Nzg5MCIsICJ1c2VyIjogeyJpc19vcmdfYWRtaW4iOiB0cnVlfX19"
            )
        }
        actual = insights.generate_http_identity_headers(
            known_account_number, is_org_admin=True
        )
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
    def test_get_sources_authentication_not_found(self, mock_get):
        """Assert get_sources_authentication returns None if not found."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        endpoint = insights.get_sources_authentication(
            self.account_number, self.authentication_id
        )
        self.assertIsNone(endpoint)
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

    @patch("requests.get")
    def test_get_sources_authentication_fail_500(self, mock_get):
        """Assert get_sources_authentication fails when response is not-200/404."""
        mock_get.return_value.status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR
        with self.assertRaises(SourcesAPINotOkStatus):
            insights.get_sources_authentication(
                self.account_number, self.authentication_id
            )

        mock_get.assert_called()

    def test_get_x_rh_identity_header_success(self):
        """Assert get_x_rh_identity_header succeeds for a valid header."""
        expected_value = {"identity": {"account_number": _faker.pyint()}}
        encoded_value = base64.b64encode(json.dumps(expected_value).encode("utf-8"))
        headers = ((_faker.slug(), _faker.slug()), ("x-rh-identity", encoded_value))

        extracted_value = insights.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, expected_value)

    def test_get_x_rh_identity_header_missing(self):
        """Assert get_x_rh_identity_header returns empty dict if not found."""
        headers = ((_faker.slug(), _faker.slug()),)

        extracted_value = insights.get_x_rh_identity_header(headers)
        self.assertEqual(extracted_value, {})

    @patch("requests.get")
    def test_get_sources_application_success(self, mock_get):
        """Assert get_sources_application returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        application = insights.get_sources_application(
            self.account_number, self.application_id
        )
        self.assertEqual(application, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_application_fail(self, mock_get):
        """Assert get_sources_application returns None if not found."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        application = insights.get_sources_application(
            self.account_number, self.application_id
        )
        self.assertIsNone(application)
        mock_get.assert_called()

    @patch("requests.get")
    def test_list_sources_application_authentications_success(self, mock_get):
        """Assert list_sources_application_authentications returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        application = insights.list_sources_application_authentications(
            self.account_number, self.authentication_id
        )
        self.assertEqual(application, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_cloudigrade_application_type_success(self, mock_get):
        """Assert get_sources_cloudigrade_application_type_id returns id."""
        cloudigrade_app_type_id = _faker.pyint()
        expected = {"data": [{"id": cloudigrade_app_type_id}]}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        response_app_type_id = insights.get_sources_cloudigrade_application_type_id(
            self.account_number
        )
        self.assertEqual(response_app_type_id, cloudigrade_app_type_id)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_cloudigrade_application_type_fail(self, mock_get):
        """Assert get_sources_cloudigrade_application_type_id returns None."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        response_app_type_id = insights.get_sources_cloudigrade_application_type_id(
            self.account_number
        )
        self.assertIsNone(response_app_type_id)
        mock_get.assert_called()

    @patch("requests.patch")
    def test_notify_sources_application_availability_success(self, mock_patch):
        """Test notify sources happy path success."""
        application_id = _faker.pyint()
        availability_status = "available"
        mock_patch.return_value.status_code = http.HTTPStatus.NO_CONTENT

        insights.notify_sources_application_availability(
            self.account_number, application_id, availability_status=availability_status
        )
        mock_patch.assert_called()

    @patch("requests.patch")
    def test_notify_sources_application_availability_skip(self, mock_patch):
        """Test notify sources skips if not enabled."""
        application_id = _faker.pyint()
        availability_status = "available"

        with override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False):
            insights.notify_sources_application_availability(
                self.account_number,
                application_id,
                availability_status=availability_status,
            )
        mock_patch.assert_not_called()

    @patch("requests.patch")
    def test_notify_sources_application_availability_not_found(self, mock_patch):
        """Test 404 status for patching sources."""
        application_id = _faker.pyint()
        availability_status = "available"

        mock_patch.return_value.status_code = http.HTTPStatus.NOT_FOUND

        with self.assertLogs("util.insights", level="INFO") as logger:
            insights.notify_sources_application_availability(
                self.account_number,
                application_id,
                availability_status=availability_status,
            )
            self.assertIn("Cannot update availability", logger.output[1])

        mock_patch.assert_called()

    @patch("requests.patch")
    def test_notify_sources_application_availability_other_status(self, mock_patch):
        """Test unknown status for patching sources."""
        application_id = _faker.pyint()
        availability_status = "available"

        mock_patch.return_value.status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR

        with self.assertRaises(SourcesAPINotOkStatus):
            insights.notify_sources_application_availability(
                self.account_number,
                application_id,
                availability_status=availability_status,
            )

        mock_patch.assert_called()
