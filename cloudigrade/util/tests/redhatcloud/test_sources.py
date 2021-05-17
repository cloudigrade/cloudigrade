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
from util.redhatcloud import sources

_faker = faker.Faker()


class SourcesTest(TestCase):
    """Red Hat Cloud sources module test case."""

    def setUp(self):
        """Set up test data."""
        self.account_number = str(_faker.pyint())
        self.authentication_id = _faker.user_name()
        self.application_id = _faker.pyint()
        self.listener_server = "test_kafka_server"
        self.listener_port = "19092"
        self.sources_resource_type = "test_application"
        self.sources_kafka_topic = "test_availability_status_topic"
        self.sources_availability_event_type = "test_availability_status"

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

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_success(
        self,
        mock_kafka_producer,
    ):
        """Test notify sources happy path success."""
        application_id = _faker.pyint()
        availability_status = "available"

        sources_kafka_config = {
            "bootstrap.servers": f"{self.listener_server}:{self.listener_port}"
        }

        kafka_producer = mock_kafka_producer(sources_kafka_config)

        with override_settings(
            LISTENER_SERVER=self.listener_server,
            LISTENER_PORT=self.listener_port,
            SOURCES_STATUS_TOPIC=self.sources_kafka_topic,
            SOURCES_RESOURCE_TYPE=self.sources_resource_type,
            SOURCES_AVAILABILITY_EVENT_TYPE=self.sources_availability_event_type,
            SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=True,
        ):
            sources.notify_application_availability(
                application_id,
                availability_status=availability_status,
            )

        payload = {
            "resource_type": self.sources_resource_type,
            "resource_id": application_id,
            "status": availability_status,
            "error": "",
        }

        kafka_producer.poll.assert_called_once_with(0)
        kafka_producer.produce.assert_called_with(
            topic=self.sources_kafka_topic,
            value=json.dumps(payload),
            headers={"event_type": self.sources_availability_event_type},
        )
        kafka_producer.flush.assert_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_skip(
        self,
        mock_kafka_producer,
    ):
        """Test notify source application availability skips if not enabled."""
        application_id = _faker.pyint()
        availability_status = "available"

        with override_settings(SOURCES_ENABLE_DATA_MANAGEMENT_FROM_KAFKA=False):
            sources.notify_application_availability(
                application_id,
                availability_status=availability_status,
            )
        mock_kafka_producer.assert_not_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_buffer_error(
        self,
        mock_kafka_producer,
    ):
        """Test notify source application availability handling BufferError."""
        application_id = _faker.pyint()
        availability_status = "available"

        sources_kafka_config = {
            "bootstrap.servers": f"{self.listener_server}:{self.listener_port}"
        }

        kafka_producer = mock_kafka_producer(sources_kafka_config)
        kafka_producer.produce.side_effect = BufferError("bad error")

        payload = {
            "resource_type": self.sources_resource_type,
            "resource_id": application_id,
            "status": availability_status,
            "error": "",
        }

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
                    application_id,
                    availability_status=availability_status,
                )

            kafka_producer.poll.assert_called_once_with(0)
            kafka_producer.produce.assert_called_with(
                topic=self.sources_kafka_topic,
                value=json.dumps(payload),
                headers={"event_type": self.sources_availability_event_type},
            )
            kafka_producer.flush.assert_not_called()

    @patch("util.redhatcloud.sources.KafkaProducer")
    def test_notify_sources_application_availability_kafka_exception(
        self,
        mock_kafka_producer,
    ):
        """Test notify source application availability handling KafkaException."""
        application_id = _faker.pyint()
        availability_status = "available"

        sources_kafka_config = {
            "bootstrap.servers": f"{self.listener_server}:{self.listener_port}"
        }

        kafka_producer = mock_kafka_producer(sources_kafka_config)
        kafka_producer.produce.side_effect = KafkaException(KafkaError(5))

        payload = {
            "resource_type": self.sources_resource_type,
            "resource_id": application_id,
            "status": availability_status,
            "error": "",
        }

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
                    application_id,
                    availability_status=availability_status,
                )

            kafka_producer.poll.assert_called_once_with(0)
            kafka_producer.produce.assert_called_with(
                topic=self.sources_kafka_topic,
                value=json.dumps(payload),
                headers={"event_type": self.sources_availability_event_type},
            )
            kafka_producer.flush.assert_not_called()
