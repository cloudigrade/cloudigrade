"""Collection of tests for ``util.redhatcloud.sources`` module."""
import http
import json
from unittest.mock import MagicMock, Mock, patch

import faker
from confluent_kafka import KafkaError, KafkaException
from django.test import TestCase, override_settings

from util.exceptions import (
    KafkaProducerException,
    SourcesAPINotJsonContent,
    SourcesAPINotOkStatus,
)
from util.redhatcloud import identity, sources
from util.redhatcloud.sources import _check_response

_faker = faker.Faker()


class SourcesTest(TestCase):
    """Red Hat Cloud sources module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()
        self.application_id = _faker.pyint()
        self.listener_server = _faker.hostname()
        self.listener_port = str(_faker.pyint())
        self.sources_resource_type = _faker.slug()
        self.sources_kafka_topic = _faker.slug()
        self.sources_availability_event_type = _faker.slug()
        self.available_status = "available"
        self.headers = identity.generate_http_identity_headers(
            self.account_number, is_org_admin=True
        )
        self.sources_kafka_config = {
            "bootstrap.servers": f"{self.listener_server}:{self.listener_port}"
        }
        self.kafka_payload = {
            "resource_type": self.sources_resource_type,
            "resource_id": self.application_id,
            "status": self.available_status,
            "error": "",
        }

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
    def test_get_sources_cloudigrade_application_type_is_cached(self, mock_get):
        """Assert get_cloudigrade_application_type_id returns cached id."""
        cloudigrade_app_type_id = _faker.pyint()
        expected = {"data": [{"id": cloudigrade_app_type_id}]}
        mock_get.return_value.status_code = http.HTTPStatus.OK
        mock_get.return_value.json.return_value = expected

        response_app_type_id = sources.get_cloudigrade_application_type_id(
            self.account_number
        )
        self.assertEqual(response_app_type_id, cloudigrade_app_type_id)

        """Call it again and make sure the original, cached value is returened"""
        not_cloudigrade_app_type_id = _faker.pyint()
        not_expected = {"data": [{"id": not_cloudigrade_app_type_id}]}
        mock_get.return_value.json.return_value = not_expected

        response_app_type_id = sources.get_cloudigrade_application_type_id(
            self.account_number
        )
        self.assertEqual(response_app_type_id, cloudigrade_app_type_id)
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_get_sources_cloudigrade_application_type_fail(self, mock_get):
        """Assert get_cloudigrade_application_type_id returns None."""
        mock_get.return_value.status_code = http.HTTPStatus.NOT_FOUND

        response_app_type_id = sources.get_cloudigrade_application_type_id(
            self.account_number
        )
        self.assertIsNone(response_app_type_id)
        mock_get.assert_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_success(
        self,
        mock_kafka_producer,
    ):
        """Test notify sources happy path success."""
        kafka_producer = mock_kafka_producer(self.sources_kafka_config)

        with override_settings(
            LISTENER_SERVER=self.listener_server,
            LISTENER_PORT=self.listener_port,
            SOURCES_STATUS_TOPIC=self.sources_kafka_topic,
            SOURCES_RESOURCE_TYPE=self.sources_resource_type,
            SOURCES_AVAILABILITY_EVENT_TYPE=self.sources_availability_event_type,
            SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True,
            VERBOSE_SOURCES_NOTIFICATION_LOGGING=True,
        ):
            sources.notify_application_availability(
                self.account_number,
                self.application_id,
                availability_status=self.available_status,
            )

        kafka_producer.produce.assert_called_with(
            topic=self.sources_kafka_topic,
            value=json.dumps(self.kafka_payload),
            headers={
                "x-rh-sources-account-number": self.account_number,
                "event_type": self.sources_availability_event_type,
            },
            callback=_check_response,
        )
        kafka_producer.flush.assert_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_skip(
        self,
        mock_kafka_producer,
    ):
        """Test notify source application availability skips if not enabled."""
        with override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False):
            sources.notify_application_availability(
                self.account_number,
                self.application_id,
                availability_status=self.available_status,
            )
        mock_kafka_producer.assert_not_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_buffer_error(
        self,
        mock_kafka_producer,
    ):
        """Test notify source application availability handling BufferError."""
        kafka_producer = mock_kafka_producer(self.sources_kafka_config)
        kafka_producer.produce.side_effect = BufferError("bad error")

        with override_settings(
            LISTENER_SERVER=self.listener_server,
            LISTENER_PORT=self.listener_port,
            SOURCES_STATUS_TOPIC=self.sources_kafka_topic,
            SOURCES_RESOURCE_TYPE=self.sources_resource_type,
            SOURCES_AVAILABILITY_EVENT_TYPE=self.sources_availability_event_type,
            SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True,
        ):
            with self.assertRaises(KafkaProducerException):
                sources.notify_application_availability(
                    self.account_number,
                    self.application_id,
                    availability_status=self.available_status,
                )

            kafka_producer.produce.assert_called_with(
                topic=self.sources_kafka_topic,
                value=json.dumps(self.kafka_payload),
                headers={
                    "x-rh-sources-account-number": self.account_number,
                    "event_type": self.sources_availability_event_type,
                },
                callback=_check_response,
            )
            kafka_producer.flush.assert_not_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_kafka_exception(
        self,
        mock_kafka_producer,
    ):
        """Test notify source application availability handling KafkaException."""
        kafka_producer = mock_kafka_producer(self.sources_kafka_config)
        kafka_producer.produce.side_effect = KafkaException(KafkaError(5))

        with override_settings(
            LISTENER_SERVER=self.listener_server,
            LISTENER_PORT=self.listener_port,
            SOURCES_STATUS_TOPIC=self.sources_kafka_topic,
            SOURCES_RESOURCE_TYPE=self.sources_resource_type,
            SOURCES_AVAILABILITY_EVENT_TYPE=self.sources_availability_event_type,
            SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True,
        ):
            with self.assertRaises(KafkaProducerException):
                sources.notify_application_availability(
                    self.account_number,
                    self.application_id,
                    availability_status=self.available_status,
                )

            kafka_producer.produce.assert_called_with(
                topic=self.sources_kafka_topic,
                value=json.dumps(self.kafka_payload),
                headers={
                    "x-rh-sources-account-number": self.account_number,
                    "event_type": self.sources_availability_event_type,
                },
                callback=_check_response,
            )
            kafka_producer.flush.assert_not_called()

    def test_check_response_success(self):
        """Assert _check_response logs a debug message on success."""
        with self.assertLogs("util.redhatcloud.sources", level="DEBUG") as logs:
            error = None
            message = "Successful message."
            _check_response(error, message)

        self.assertIn("DEBUG", logs.output[0])
        self.assertIn(message, logs.output[0])

    def test_check_response_success_verbose(self):
        """Assert _check_response logs an info message on success when verbose."""
        with self.settings(VERBOSE_SOURCES_NOTIFICATION_LOGGING=True):
            with self.assertLogs("util.redhatcloud.sources", level="INFO") as logs:
                error = None
                message = "Successful message."
                _check_response(error, message)

        self.assertIn("INFO", logs.output[0])
        self.assertIn(message, logs.output[0])

    def test_check_response_error(self):
        """Assert _check_response logs an error message when encountering one."""
        with self.assertLogs("util.redhatcloud.sources", level="ERROR") as logs:
            error = "An error."
            message = "A message."
            fail_message = "Failed to deliver message"
            _check_response(error, message)

        self.assertIn("ERROR", logs.output[0])
        self.assertIn(error, logs.output[0])
        self.assertIn(fail_message, logs.output[0])
