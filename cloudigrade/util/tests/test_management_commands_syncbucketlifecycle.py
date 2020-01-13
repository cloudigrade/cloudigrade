"""Collection of tests for the 'syncbucketlifecycle' management command."""
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase


class SyncBucketLifecycleTest(TestCase):
    """Management command 'syncbucketlifecycle' test case."""

    def test_command_output(self):
        """Test that 'syncbucketlifecycle' correctly calls S3 api."""
        _path = "util.management.commands.syncbucketlifecycle"
        with patch("{}.boto3".format(_path)) as mock_boto3:
            call_command("syncbucketlifecycle")

            LC_IA = settings.S3_BUCKET_LC_IA_TRANSITION
            LC_GLACIER = settings.S3_BUCKET_LC_GLACIER_TRANSITION

            mock_boto3.resource.assert_called_with("s3")

            mock_s3 = mock_boto3.resource()
            mock_s3.BucketLifecycleConfiguration.assert_called_with(
                settings.S3_BUCKET_NAME
            )

            mock_bucket_lc = mock_s3.BucketLifecycleConfiguration()
            mock_bucket_lc.put.assert_called_with(
                LifecycleConfiguration={
                    "Rules": [
                        {
                            "Expiration": {"Days": settings.S3_BUCKET_LC_MAX_AGE},
                            "ID": settings.S3_BUCKET_LC_NAME,
                            "Status": "Enabled",
                            "Filter": {"Prefix": ""},
                            "Transitions": [
                                {"Days": LC_IA, "StorageClass": "STANDARD_IA"},
                                {"Days": LC_GLACIER, "StorageClass": "GLACIER"},
                            ],
                        }
                    ]
                }
            )
