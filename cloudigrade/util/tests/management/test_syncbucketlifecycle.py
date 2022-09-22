"""Collection of tests for the 'syncbucketlifecycle' management command."""
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from util.leaderrun import LeaderRun


class SyncBucketLifecycleTest(TestCase):
    """Management command 'syncbucketlifecycle' test case."""

    def test_command_output(self):
        """Test that 'syncbucketlifecycle' correctly calls S3 api."""
        leader = LeaderRun("sync-bucket-lifecycle")
        leader.reset()
        _path = "util.management.commands.syncbucketlifecycle"
        with patch("{}.boto3".format(_path)) as mock_boto3, self.assertLogs(
            _path, level="INFO"
        ) as logging_watcher:
            call_command("syncbucketlifecycle")
            self.assertTrue(
                "SyncBucketLifeCycle: Executing" in logging_watcher.output[0]
            )

            LC_IA = settings.AWS_S3_BUCKET_LC_IA_TRANSITION
            LC_GLACIER = settings.AWS_S3_BUCKET_LC_GLACIER_TRANSITION

            mock_boto3.resource.assert_called_with("s3")

            mock_s3 = mock_boto3.resource()
            mock_s3.BucketLifecycleConfiguration.assert_any_call(
                settings.HOUNDIGRADE_RESULTS_BUCKET_NAME
            )
            mock_s3.BucketLifecycleConfiguration.assert_any_call(
                settings.AWS_S3_BUCKET_NAME,
            )

            mock_bucket_lc = mock_s3.BucketLifecycleConfiguration()
            mock_bucket_lc.put.assert_called_with(
                LifecycleConfiguration={
                    "Rules": [
                        {
                            "Expiration": {"Days": settings.AWS_S3_BUCKET_LC_MAX_AGE},
                            "ID": settings.AWS_S3_BUCKET_LC_NAME,
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

    def test_command_does_not_run_if_completed(self):
        """Test that 'syncbucketlifecycle' does not run if it already ran."""
        leader = LeaderRun("sync-bucket-lifecycle")
        leader.set_as_completed()
        _path = "util.management.commands.syncbucketlifecycle"
        with patch("{}.boto3".format(_path)) as mock_boto3, self.assertLogs(
            _path, level="INFO"
        ) as logging_watcher:
            call_command("syncbucketlifecycle")
            self.assertTrue(
                "SyncBucketLifeCycle: Already completed, Skipping"
                in logging_watcher.output[0]
            )
            mock_boto3.assert_not_called()

    @patch("util.management.commands.syncbucketlifecycle.LeaderRun")
    def test_command_does_not_run_if_running(self, mock_leaderrun):
        """Test that 'syncbucketlifecycle' does not run if currently running."""
        mock_leader = mock_leaderrun("sync-bucket-lifecycle")
        mock_leader.has_completed.return_value = False
        mock_leader.is_running.return_value = True
        mock_leader.wait_for_completion.return_value = None
        _path = "util.management.commands.syncbucketlifecycle"
        with patch("{}.boto3".format(_path)) as mock_boto3, self.assertLogs(
            _path, level="INFO"
        ) as logging_watcher:
            call_command("syncbucketlifecycle")
            self.assertTrue(
                "SyncBucketLifeCycle: Already running, Skipping"
                in logging_watcher.output[0]
            )
            mock_boto3.assert_not_called()
