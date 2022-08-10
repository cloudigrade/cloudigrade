"""Collection of tests for the internal cdappconfig.json view."""
import json
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory

from internal import views


class GetCdAppConfigJsonViewTest(TestCase):
    """get_cdappconfig_json view test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.factory = APIRequestFactory()
        self.original_config = {"hello": "world", "secret": "precious"}
        self.redacted_config = {"hello": "world", "secret": "******************us"}
        self.invalid_json_config = "hello world"

        os_environ_patch = patch("internal.views.os.environ")
        self.mock_os_environ = os_environ_patch.start()
        self.addCleanup(os_environ_patch.stop)

    def write_config_and_call_api(self, file_content):
        """Write file_content to a temporary config file and call the API."""
        with tempfile.NamedTemporaryFile("w+") as config_file:
            self.mock_os_environ.get.return_value = config_file.name
            config_file.write(file_content)
            config_file.flush()
            request = self.factory.get("/internal/cdappconfig.json")
            response = views.get_cdappconfig_json(request)
        return response

    @patch.object(views, "isClowderEnabled", return_value=True)
    @override_settings(IS_PRODUCTION=True)
    def test_get_cdappconfig_json_redacted_in_production(self, *args):
        """Test cdappconfig.json response is redacted if in production."""
        file_content = json.dumps(self.original_config)
        response = self.write_config_and_call_api(file_content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.redacted_config)

    @patch.object(views, "isClowderEnabled", return_value=True)
    @override_settings(IS_PRODUCTION=False)
    def test_get_cdappconfig_json_not_redacted_not_in_production(self, *args):
        """Test cdappconfig.json response is not redacted if not in production."""
        file_content = json.dumps(self.original_config)
        response = self.write_config_and_call_api(file_content)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.original_config)

    @patch.object(views, "isClowderEnabled", return_value=False)
    def test_get_cdappconfig_json_clowder_not_enabled(self, *args):
        """Test cdappconfig.json returns 404 if Clowder is not enabled."""
        request = self.factory.get("/internal/cdappconfig.json")
        response = views.get_cdappconfig_json(request)
        self.assertEqual(response.status_code, 404)

    @patch.object(views, "isClowderEnabled", return_value=True)
    def test_get_cdappconfig_json_invalid_file_server_error(self, *args):
        """Test cdappconfig.json response 500 if config file cannot be loaded."""
        response = self.write_config_and_call_api(self.invalid_json_config)
        self.assertEqual(response.status_code, 500)
