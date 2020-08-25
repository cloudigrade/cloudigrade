"""Collection of tests for aws.tasks.inspection.check_cluster_instance_age."""
from datetime import timedelta
from unittest.mock import patch
from unittest.util import safe_repr

from django.test import TestCase, override_settings

from api.clouds.aws.tasks import inspection
from util.tests import helper


TEST_TIME = helper.utc_dt(2019, 7, 25, 15, 30, 0)


class CheckClusterInstanceAgeTest(TestCase):
    """Helper function 'check_cluster_instance_age' test cases."""

    def assertInLog(self, member, container, level="INFO", msg=None):
        """Just like self.assertIn(member, container), but with a log level check."""
        self.assertIn(member, container)
        if not container.startswith(f"{level}:"):
            # This implementation is consistent with similar functions in unittest.case.
            standardMsg = "%s does not start with %s" % (
                safe_repr(container),
                safe_repr(level),
            )
            self.fail(self._formatMessage(msg, standardMsg))

    @patch("api.clouds.aws.tasks.inspection.boto3")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_check_cluster_instances_age_no_instance_ids(self, mock_aws, mock_boto3):
        """Assert early return if no instance ids are given."""
        inspection.check_cluster_instances_age([])
        mock_aws.describe_instances.assert_not_called()
        mock_boto3.Session.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.boto3")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_check_cluster_instances_age_no_launch_time(self, mock_aws, mock_boto3):
        """Assert logs info and errors if no launch times from AWS."""
        instance_id_1 = helper.generate_dummy_instance_id()
        instance_id_2 = helper.generate_dummy_instance_id()
        instance_ids = [instance_id_1, instance_id_2]
        mock_aws.describe_instances.return_value = dict(
            (
                instance_id,
                helper.generate_dummy_describe_instance(instance_id, launch_time=None),
            )
            for instance_id in instance_ids
        )

        with self.assertLogs(
            "api.clouds.aws.tasks.inspection", level="INFO"
        ) as logging_watcher:
            inspection.check_cluster_instances_age(instance_ids)

        self.assertEqual(len(logging_watcher.output), 4)
        self.assertInLog(instance_id_1, logging_watcher.output[0])
        self.assertInLog(instance_id_2, logging_watcher.output[1])
        self.assertInLog(instance_id_1, logging_watcher.output[2], "ERROR")
        self.assertInLog(instance_id_2, logging_watcher.output[3], "ERROR")
        self.assertInLog("no launch time", logging_watcher.output[2], "ERROR")
        self.assertInLog("no launch time", logging_watcher.output[3], "ERROR")

        mock_boto3.Session.assert_called_once()
        mock_aws.describe_instances.assert_called_once_with(
            mock_boto3.Session.return_value, instance_ids, mock_aws.ECS_CLUSTER_REGION,
        )

    @helper.clouditardis(TEST_TIME)
    @override_settings(INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT=600)
    @patch("api.clouds.aws.tasks.inspection.boto3")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_check_cluster_instances_under_limit(self, mock_aws, mock_boto3):
        """Assert logs info and debug if launch times are under the configured limit."""
        instance_id_1 = helper.generate_dummy_instance_id()
        instance_id_2 = helper.generate_dummy_instance_id()
        instance_ids = [instance_id_1, instance_id_2]
        launch_time = TEST_TIME - timedelta(seconds=10)  # less than 600 seconds older
        mock_aws.describe_instances.return_value = dict(
            (
                instance_id,
                helper.generate_dummy_describe_instance(
                    instance_id, launch_time=launch_time
                ),
            )
            for instance_id in instance_ids
        )

        with self.assertLogs(
            "api.clouds.aws.tasks.inspection", level="DEBUG"
        ) as logging_watcher:
            inspection.check_cluster_instances_age(instance_ids)

        self.assertEqual(len(logging_watcher.output), 4)
        self.assertInLog(instance_id_1, logging_watcher.output[0])
        self.assertInLog(instance_id_2, logging_watcher.output[1])
        self.assertInLog(instance_id_1, logging_watcher.output[2], "DEBUG")
        self.assertInLog(instance_id_2, logging_watcher.output[3], "DEBUG")
        self.assertInLog("fits within", logging_watcher.output[2], "DEBUG")
        self.assertInLog("10.0 seconds", logging_watcher.output[2], "DEBUG")
        self.assertInLog("fits within", logging_watcher.output[3], "DEBUG")
        self.assertInLog("10.0 seconds", logging_watcher.output[3], "DEBUG")

        mock_boto3.Session.assert_called_once()
        mock_aws.describe_instances.assert_called_once_with(
            mock_boto3.Session.return_value, instance_ids, mock_aws.ECS_CLUSTER_REGION,
        )

    @helper.clouditardis(TEST_TIME)
    @override_settings(INSPECTION_CLUSTER_INSTANCE_AGE_LIMIT=600)
    @patch("api.clouds.aws.tasks.inspection.boto3")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_check_cluster_instances_exceed_limit(self, mock_aws, mock_boto3):
        """Assert logs info and error if launch times exceed the configured limit."""
        instance_id_1 = helper.generate_dummy_instance_id()
        instance_id_2 = helper.generate_dummy_instance_id()
        instance_ids = [instance_id_1, instance_id_2]
        launch_time = TEST_TIME - timedelta(seconds=999)  # more than 600 seconds older
        mock_aws.describe_instances.return_value = dict(
            (
                instance_id,
                helper.generate_dummy_describe_instance(
                    instance_id, launch_time=launch_time
                ),
            )
            for instance_id in instance_ids
        )

        with self.assertLogs(
            "api.clouds.aws.tasks.inspection", level="INFO"
        ) as logging_watcher:
            inspection.check_cluster_instances_age(instance_ids)

        self.assertEqual(len(logging_watcher.output), 4)
        self.assertInLog(instance_id_1, logging_watcher.output[0])
        self.assertInLog(instance_id_2, logging_watcher.output[1])
        self.assertInLog(instance_id_1, logging_watcher.output[2], "ERROR")
        self.assertInLog(instance_id_2, logging_watcher.output[3], "ERROR")
        self.assertInLog("exceeds", logging_watcher.output[2], "ERROR")
        self.assertInLog("999.0 seconds", logging_watcher.output[2], "ERROR")
        self.assertInLog("exceeds", logging_watcher.output[3], "ERROR")
        self.assertInLog("999.0 seconds", logging_watcher.output[3], "ERROR")

        mock_boto3.Session.assert_called_once()
        mock_aws.describe_instances.assert_called_once_with(
            mock_boto3.Session.return_value, instance_ids, mock_aws.ECS_CLUSTER_REGION,
        )
