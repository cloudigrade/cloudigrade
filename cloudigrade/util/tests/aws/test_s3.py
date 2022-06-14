"""Collection of tests for ``util.aws.s3`` module."""
import gzip
import io
from unittest.mock import patch

from django.test import TestCase

from util.aws import s3
from util.tests import helper


class UtilAwsS3Test(TestCase):
    """AWS S3 utility functions test case."""

    def setUp(self):
        """Set up common variables for tests."""
        self.aws_account_id = helper.generate_dummy_aws_account_id()
        self.uncompressed_file_key = f"AWSLogs/{self.aws_account_id}/path/to/file"
        self.compressed_file_key = f"{self.uncompressed_file_key}.gz"

    def test_get_object_content_from_s3_gzipped_name(self):
        """Assert that .gz file name is handled as gzipped data."""
        bucket = "test_bucket"
        key = self.compressed_file_key
        content_bytes = b'{"Key": "Value"}'
        byte_stream = io.BytesIO(gzip.compress(content_bytes))
        object_body = {
            "Body": byte_stream,
        }

        with patch.object(s3, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = object_body

            actual_content = s3.get_object_content_from_s3(bucket, key)

        self.assertEqual(content_bytes.decode("utf-8"), actual_content)

    def test_get_object_content_from_s3_gzipped_content_type(self):
        """Assert that gzip content type is handled."""
        bucket = "test_bucket"
        key = self.uncompressed_file_key
        content_bytes = b'{"Key": "Value"}'
        byte_stream = io.BytesIO(gzip.compress(content_bytes))
        object_body = {
            "Body": byte_stream,
            "ContentType": "application/x-gzip",
        }

        with patch.object(s3, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = object_body

            actual_content = s3.get_object_content_from_s3(bucket, key)

        self.assertEqual(content_bytes.decode("utf-8"), actual_content)

    def test_get_object_content_from_s3_uncompressed(self):
        """Assert that uncompressed content is handled."""
        bucket = "test_bucket"
        key = self.uncompressed_file_key
        content_bytes = b'{"Key": "Value"}'
        byte_stream = io.BytesIO(content_bytes)
        object_body = {
            "Body": byte_stream,
            "ContentType": "application/json",
        }

        with patch.object(s3, "boto3") as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = object_body

            actual_content = s3.get_object_content_from_s3(bucket, key)

        self.assertEqual(content_bytes.decode("utf-8"), actual_content)

    def test_get_object_content_from_s3_uncompressed_not_utf8_error(self):
        """Assert that not-gzipped not-utf8 bits raise an appropriate error."""
        bucket = "test_bucket"
        key = self.uncompressed_file_key
        content_bytes = bytes.fromhex("deadbeef")  # not utf-8 safe!
        byte_stream = io.BytesIO(content_bytes)
        object_body = {"Body": byte_stream}

        with patch.object(s3, "boto3") as mock_boto3, self.assertRaises(
            UnicodeDecodeError
        ):
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = object_body

            s3.get_object_content_from_s3(bucket, key)
