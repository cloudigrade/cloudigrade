"""Collection of tests for the internal sources_kafka view."""

from django.test import TestCase

from api.tests import helper as api_helper


class SourcesKafkaViewTest(TestCase):
    """Internal sources_kafka view test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.client = api_helper.SandboxedRestClient(api_root="/internal")

    def test_sources_kafka_invalid_header(self):
        """Assert that an invalid header to sources_kafka returns 400."""
        response = self.client.post_sources_kafka(
            data={"headers": "invalid_base64_header"}
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["headers"], "headers is not valid base64 encoded json")
