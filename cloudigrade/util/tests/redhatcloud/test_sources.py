"""Collection of tests for ``util.redhatcloud.sources`` module."""
import http
import json
from unittest.mock import MagicMock, Mock, patch

import faker
from django.test import TestCase, override_settings

from util.exceptions import SourcesAPINotJsonContent, SourcesAPINotOkStatus
from util.redhatcloud import sources

_faker = faker.Faker()


class SourcesTest(TestCase):
    """Red Hat Cloud sources module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()
        self.application_id = _faker.pyint()

    @patch("requests.get")
    def test_get_sources_authentication_success(self, mock_get):
        """Assert get_authentication returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        authentication = sources.get_authentication(
            self.account_number, self.authentication_id
        )
        self.assertEqual(authentication, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_not_found(self, mock_get):
        """Assert get_authentication returns None if not found."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        endpoint = sources.get_authentication(
            self.account_number, self.authentication_id
        )
        self.assertIsNone(endpoint)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_fail_not_json(self, mock_get):
        """Assert get_authentication fails when response isn't JSON."""
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.side_effect = json.decoder.JSONDecodeError(
            Mock(), MagicMock(), MagicMock()
        )
        with self.assertRaises(SourcesAPINotJsonContent):
            sources.get_authentication(self.account_number, self.authentication_id)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_authentication_fail_500(self, mock_get):
        """Assert get_authentication fails when response is not-200/404."""
        mock_get.return_value.status_code = http.HTTPStatus.INTERNAL_SERVER_ERROR
        with self.assertRaises(SourcesAPINotOkStatus):
            sources.get_authentication(self.account_number, self.authentication_id)

        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_application_success(self, mock_get):
        """Assert get_application returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        application = sources.get_application(self.account_number, self.application_id)
        self.assertEqual(application, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_application_fail(self, mock_get):
        """Assert get_application returns None if not found."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        application = sources.get_application(self.account_number, self.application_id)
        self.assertIsNone(application)
        mock_get.assert_called()

    @patch("requests.get")
    def test_list_sources_application_authentications_success(self, mock_get):
        """Assert list_application_authentications returns response content."""
        expected = {"hello": "world"}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        application = sources.list_application_authentications(
            self.account_number, self.authentication_id
        )
        self.assertEqual(application, expected)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_cloudigrade_application_type_success(self, mock_get):
        """Assert get_cloudigrade_application_type_id returns id."""
        cloudigrade_app_type_id = _faker.pyint()
        expected = {"data": [{"id": cloudigrade_app_type_id}]}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        response_app_type_id = sources.get_cloudigrade_application_type_id(
            self.account_number
        )
        self.assertEqual(response_app_type_id, cloudigrade_app_type_id)
        mock_get.assert_called()

    @patch("requests.get")
    def test_get_sources_cloudigrade_application_type_fail(self, mock_get):
        """Assert get_cloudigrade_application_type_id returns None."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        response_app_type_id = sources.get_cloudigrade_application_type_id(
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

        sources.notify_application_availability(
            self.account_number, application_id, availability_status=availability_status
        )
        mock_patch.assert_called()

    @patch("requests.patch")
    def test_notify_sources_application_availability_skip(self, mock_patch):
        """Test notify sources skips if not enabled."""
        application_id = _faker.pyint()
        availability_status = "available"

        with override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False):
            sources.notify_application_availability(
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

        with self.assertLogs("util.redhatcloud.sources", level="INFO") as logger:
            sources.notify_application_availability(
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
            sources.notify_application_availability(
                self.account_number,
                application_id,
                availability_status=availability_status,
            )

        mock_patch.assert_called()
