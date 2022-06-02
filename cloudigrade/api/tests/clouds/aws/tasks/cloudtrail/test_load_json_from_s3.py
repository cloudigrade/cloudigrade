"""Collection of tests for aws.tasks.clouds.aws.tasks.cloudtrail.load_json_from_s3."""
import json
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.aws.tasks.cloudtrail import load_json_from_s3

_faker = faker.Faker()


class LoadJsonFromS33Test(TestCase):
    """Helper function 'load_json_from_s3' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.bucket = _faker.slug()
        self.key = f"/{_faker.slug()}/{_faker.slug()}/_faker.slug()"

    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    def test_load_json_from_s3(self, mock_get_object_content_from_s3):
        """Test load_json_from_s3 happy path."""
        original_message = {_faker.slug(): _faker.slug()}
        json_message = json.dumps(original_message)
        mock_get_object_content_from_s3.return_value = json_message
        actual_results = load_json_from_s3(self.bucket, self.key)
        self.assertEqual(original_message, actual_results)

    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    def test_get_object_content_from_s3_failed(self, mock_get_object_content_from_s3):
        """Test load_json_from_s3 failure when s3 raises unexpected exception."""

        class UnexpectedException(Exception):
            """Custom unexpected exception for this test."""

        error_message = _faker.sentence()
        error = UnexpectedException(error_message)
        mock_get_object_content_from_s3.side_effect = error
        with self.assertRaises(UnexpectedException) as error_cm, self.assertLogs(
            "api.clouds.aws.tasks.cloudtrail", level="ERROR"
        ) as log_context:
            load_json_from_s3(self.bucket, self.key)
        self.assertEqual(error_message, error_cm.exception.args[0])
        self.assertIn(
            f"Unexpected failure ({error_message}) getting object content from S3",
            log_context.records[0].message,
        )

    @patch("api.clouds.aws.tasks.cloudtrail.aws.get_object_content_from_s3")
    def test_json_loads_failed(self, mock_get_object_content_from_s3):
        """Test load_json_from_s3 returns None when message cannot parse to JSON."""
        not_json_content = _faker.sentence()
        mock_get_object_content_from_s3.return_value = not_json_content
        with self.assertLogs(
            "api.clouds.aws.tasks.cloudtrail", level="ERROR"
        ) as log_context:
            actual_results = load_json_from_s3(self.bucket, self.key)
        logged_message = log_context.records[0].message
        self.assertTrue(logged_message.startswith("Unexpected failure ("))
        self.assertIn(" in json.loads from S3", logged_message)
        self.assertIsNone(actual_results)
