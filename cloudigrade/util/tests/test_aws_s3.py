"""Collection of tests for ``util.aws.s3`` module."""
import gzip
import io
from unittest.mock import patch

from django.test import TestCase

from util.aws import s3


class UtilAwsS3Test(TestCase):
    """AWS S3 utility functions test case."""

    def test_get_object_content_from_s3_gzipped(self):
        """Assert that gzipped content is handled."""
        mock_bucket = 'test_bucket'
        mock_key = '/path/to/file'
        mock_content_bytes = b'{"Key": "Value"}'
        mock_byte_stream = io.BytesIO(gzip.compress(mock_content_bytes))
        mock_object_body = {'Body': mock_byte_stream}

        with patch.object(s3, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = mock_object_body

            actual_content = s3.get_object_content_from_s3(
                mock_bucket,
                mock_key
            )

        self.assertEqual(mock_content_bytes.decode('utf-8'), actual_content)

    def test_get_object_content_from_s3_uncompressed(self):
        """Assert that uncompressed content is handled."""
        mock_bucket = 'test_bucket'
        mock_key = '/path/to/file'
        mock_content_bytes = b'{"Key": "Value"}'
        mock_byte_stream = io.BytesIO(mock_content_bytes)
        mock_object_body = {'Body': mock_byte_stream}

        with patch.object(s3, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = mock_object_body

            actual_content = s3.get_object_content_from_s3(
                mock_bucket,
                mock_key,
                compression=None
            )

        self.assertEqual(mock_content_bytes.decode('utf-8'), actual_content)

    def test_get_object_content_from_s3_unsupported_compression(self):
        """Assert that unhandled compression does not return content."""
        mock_bucket = 'test_bucket'
        mock_key = '/path/to/file'
        mock_content_bytes = b'{"Key": "Value"}'
        mock_byte_stream = io.BytesIO(mock_content_bytes)
        mock_object_body = {'Body': mock_byte_stream}

        with patch.object(s3, 'boto3') as mock_boto3:
            mock_resource = mock_boto3.resource.return_value
            mock_s3_object = mock_resource.Object.return_value
            mock_s3_object.get.return_value = mock_object_body

            actual_content = s3.get_object_content_from_s3(
                mock_bucket,
                mock_key,
                compression='bzip'
            )

        self.assertIsNone(actual_content)
