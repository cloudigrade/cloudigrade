"""Collection of tests for internal Redis raw command API."""
import json
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from internal.serializers import InternalRedisRawInputSerializer
from internal.views import redis_raw

_faker = faker.Faker()


class RedisRawViewTest(TestCase):
    """Redis raw command API view test case."""

    def setUp(self):
        """Set up shared test data."""
        self.factory = APIRequestFactory()
        get_redis_connection_patch = patch("internal.views.redis.get_redis_connection")
        mock_get_redis_connection = get_redis_connection_patch.start()
        self.mock_connection = (
            mock_get_redis_connection.return_value.__enter__.return_value
        )
        self.addCleanup(get_redis_connection_patch.stop)

    def assertExpectedJsonResponse(self, response, expected):
        """Assert expected is equal to response rendered as JSON."""
        response.render()
        response_json_decoded = json.loads(response.content.decode("utf-8"))
        self.assertEqual(response_json_decoded, expected)

    def test_supported_command_and_args(self):
        """Test happy path success for running a command with args."""
        command = _faker.random_element(
            InternalRedisRawInputSerializer.allowed_commands
        )
        args = _faker.word()
        request = self.factory.post(
            "/redis_raw/", data={"command": command, "args": args}, format="json"
        )

        redis_command_results = _faker.sentence()
        mock_func = getattr(self.mock_connection, command)
        mock_func.return_value = redis_command_results

        expected_response_data = {"results": redis_command_results}

        response = redis_raw(request)
        self.assertEqual(response.status_code, 200)
        self.assertExpectedJsonResponse(response, expected_response_data)

    def test_unsupported_command_fails(self):
        """Test failure path for an unsupported command."""
        command = _faker.word()
        args = _faker.word()
        request = self.factory.post(
            "/redis_raw/", data={"command": command, "args": args}, format="json"
        )

        redis_command_results = _faker.sentence()
        mock_func = getattr(self.mock_connection, command)
        mock_func.return_value = redis_command_results

        expected_response_data = {"command": [f'"{command}" is not a valid choice.']}

        response = redis_raw(request)
        self.assertEqual(response.status_code, 400)
        self.assertExpectedJsonResponse(response, expected_response_data)

    def test_invalid_argument_fails(self):
        """Test failure path for invalid arguments to the command."""
        command = _faker.random_element(
            InternalRedisRawInputSerializer.allowed_commands
        )
        args = _faker.word()
        request = self.factory.post(
            "/redis_raw/", data={"command": command, "args": args}, format="json"
        )

        error = TypeError()
        mock_func = getattr(self.mock_connection, command)
        mock_func.side_effect = error

        expected_response_data = {"error": str(error)}

        response = redis_raw(request)
        self.assertEqual(response.status_code, 400)
        self.assertExpectedJsonResponse(response, expected_response_data)

    def test_result_bytes_are_stringified(self):
        """Test a command's returned not-utf-8 bytes are stringified as expected."""
        command = _faker.random_element(
            InternalRedisRawInputSerializer.allowed_commands
        )
        args = _faker.word()
        request = self.factory.post(
            "/redis_raw/", data={"command": command, "args": args}, format="json"
        )

        redis_command_results = b"\xa0\x69"  # 0xa0 in position 0: invalid start byte
        mock_func = getattr(self.mock_connection, command)
        mock_func.return_value = redis_command_results

        expected_response_data = {"results": "b'\\xa0i'"}

        response = redis_raw(request)
        self.assertEqual(response.status_code, 200)
        self.assertExpectedJsonResponse(response, expected_response_data)
