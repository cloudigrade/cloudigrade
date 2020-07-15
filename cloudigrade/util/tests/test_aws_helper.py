"""Collection of tests for ``util.aws.helper`` module."""
import uuid
from unittest.mock import Mock, call, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from util.aws import helper
from util.tests import helper as test_helper


class UtilAwsHelperTest(TestCase):
    """AWS helper utility functions test case."""

    def test_rewrap_aws_errors_returns_inner_return(self):
        """Assert rewrap_aws_errors returns inner function's result if no exception."""

        @helper.rewrap_aws_errors
        def dummy_adder(a, b):
            return a + b

        expected_result = 3
        actual_result = dummy_adder(1, 2)
        self.assertEqual(actual_result, expected_result)

    def test_rewrap_aws_errors_raises_not_aws_clienterror(self):
        """Assert rewrap_aws_errors allows non-ClientError exceptions to raise."""

        class DummyException(Exception):
            pass

        @helper.rewrap_aws_errors
        def dummy_adder(a, b):
            raise DummyException

        with self.assertRaises(DummyException):
            dummy_adder(1, 2)

    def test_rewrap_aws_errors_quietly_logs_aws_unauthorizedoperation(self):
        """
        Assert rewrap_aws_errors quietly logs UnauthorizedOperation exceptions.

        When we encounter UnauthorizedOperation, that means we did not have permission
        to perform the operation on behalf of the customer. This should only happen if
        the customer's AWS IAM configuration has broken. When this happens, we want to
        processing to stop gracefully (such as the async tasks) and to allow the
        periodic task responsible for checking permissions to disable the account if
        necessary.
        """
        mock_error = {
            "Error": {
                "Code": "UnauthorizedOperation",
                "Message": "Something bad happened.",
            }
        }

        @helper.rewrap_aws_errors
        def dummy_adder(a, b):
            raise ClientError(mock_error, "SomeRandomAction")

        with self.assertLogs("util.aws.helper", level="WARNING") as logging_watcher:
            actual_result = dummy_adder(1, 2)
            self.assertIn("Something bad happened.", logging_watcher.output[0])

        self.assertIsNone(actual_result)

    def test_get_regions_with_no_args(self):
        """Assert get_regions with no args returns expected regions."""
        mock_region_names = [
            f"region-{uuid.uuid4()}",
            f"region-{uuid.uuid4()}",
        ]

        mock_regions = {
            "Regions": [
                {"RegionName": mock_region_names[0]},
                {"RegionName": mock_region_names[1]},
            ]
        }

        mock_client = Mock()
        mock_client.describe_regions.return_value = mock_regions
        mock_session = Mock()
        mock_session.client.return_value = mock_client
        actual_regions = helper.get_regions(mock_session)
        self.assertTrue(mock_client.describe_regions.called)
        mock_session.client.assert_called_with("ec2")
        self.assertListEqual(mock_region_names, actual_regions)

    def test_get_regions_with_custom_service(self):
        """Assert get_regions with service name returns expected regions."""
        mock_region_names = [
            f"region-{uuid.uuid4()}",
            f"region-{uuid.uuid4()}",
        ]

        mock_regions = {
            "Regions": [
                {"RegionName": mock_region_names[0]},
                {"RegionName": mock_region_names[1]},
            ]
        }

        mock_client = Mock()
        mock_client.describe_regions.return_value = mock_regions
        mock_session = Mock()
        mock_session.client.return_value = mock_client
        actual_regions = helper.get_regions(mock_session, "tng")
        self.assertTrue(mock_client.describe_regions.called)
        mock_session.client.assert_called_with("tng")
        self.assertListEqual(mock_region_names, actual_regions)

    @patch("util.aws.helper._verify_policy_action")
    def test_verify_account_access_success(self, mock_verify_policy_action):
        """Assert that account access is verified when all actions are OK."""
        mock_session = Mock()
        expected_calls = [
            call(mock_session, "ec2:DescribeImages"),
            call(mock_session, "ec2:DescribeInstances"),
            call(mock_session, "ec2:ModifySnapshotAttribute"),
            call(mock_session, "ec2:DescribeSnapshotAttribute"),
            call(mock_session, "ec2:DescribeSnapshots"),
            call(mock_session, "ec2:CopyImage"),
            call(mock_session, "ec2:CreateTags"),
            call(mock_session, "ec2:DescribeRegions"),
            call(mock_session, "cloudtrail:CreateTrail"),
            call(mock_session, "cloudtrail:UpdateTrail"),
            call(mock_session, "cloudtrail:PutEventSelectors"),
            call(mock_session, "cloudtrail:DescribeTrails"),
            call(mock_session, "cloudtrail:StartLogging"),
            call(mock_session, "cloudtrail:DeleteTrail"),
        ]
        mock_verify_policy_action.side_effect = [
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ]
        verified, failed_actions = helper.verify_account_access(mock_session)
        self.assertTrue(verified)
        self.assertEqual(len(failed_actions), 0)
        mock_verify_policy_action.assert_has_calls(expected_calls)

    @patch("util.aws.helper._verify_policy_action")
    def test_verify_account_access_failure(self, mock_verify_policy_action):
        """Assert that account access fails when some actions are not OK."""
        mock_session = Mock()
        expected_calls = [
            call(mock_session, "ec2:DescribeImages"),
            call(mock_session, "ec2:DescribeInstances"),
            call(mock_session, "ec2:ModifySnapshotAttribute"),
            call(mock_session, "ec2:DescribeSnapshotAttribute"),
            call(mock_session, "ec2:DescribeSnapshots"),
            call(mock_session, "ec2:CopyImage"),
            call(mock_session, "ec2:CreateTags"),
            call(mock_session, "ec2:DescribeRegions"),
            call(mock_session, "cloudtrail:CreateTrail"),
            call(mock_session, "cloudtrail:UpdateTrail"),
            call(mock_session, "cloudtrail:PutEventSelectors"),
            call(mock_session, "cloudtrail:DescribeTrails"),
            call(mock_session, "cloudtrail:StartLogging"),
            call(mock_session, "cloudtrail:DeleteTrail"),
        ]
        mock_verify_policy_action.side_effect = [
            True,
            True,
            True,
            False,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
        ]
        verified, failed_actions = helper.verify_account_access(mock_session)
        self.assertFalse(verified)
        self.assertEqual(len(failed_actions), 1)
        mock_verify_policy_action.assert_has_calls(expected_calls)

    def assert_verify_policy_action_success(
        self, action, function_name, func_args=(), func_kwargs=dict()
    ):
        """
        Assert _verify_policy_action succeeds with dry run "exception".

        This helper function is intended to simplify testing
        _verify_policy_action by offloading all the mocking and DryRun
        assertion stuff.

        Args:
            action (str): the action to verify
            function_name (str): the ec2 method name that would be called
            func_args (list): positional arguments that would be sent to the
                ec2 method called by _verify_policy_action
            func_kwargs (dict): keyword arguments that would be sent to the ec2
                method called by _verify_policy_action
        """
        mock_dryrun_function = Mock()
        mock_dryrun_function.side_effect = ClientError(
            error_response={"Error": {"Code": "DryRunOperation"}},
            operation_name=action,
        )
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_client.attach_mock(mock_dryrun_function, function_name)

        result = helper._verify_policy_action(mock_session, action)
        self.assertTrue(result)
        if not action.startswith("cloudtrail:"):
            mock_dryrun_function.assert_called_once_with(*func_args, **func_kwargs)

    def test_verify_policy_action_describe_images(self):
        """Assert appropriate calls to verify ec2:DescribeImages."""
        self.assert_verify_policy_action_success(
            "ec2:DescribeImages", "describe_images", func_kwargs={"DryRun": True}
        )

    def test_verify_policy_action_describe_instances(self):
        """Assert appropriate calls to verify ec2:DescribeInstances."""
        self.assert_verify_policy_action_success(
            "ec2:DescribeInstances", "describe_instances", func_kwargs={"DryRun": True}
        )

    def test_verify_policy_action_describe_snapshot_attribute(self):
        """Assert appropriate calls to verify ec2:DescribeSnapshotAttribute."""
        self.assert_verify_policy_action_success(
            "ec2:DescribeSnapshotAttribute",
            "describe_snapshot_attribute",
            func_kwargs={
                "DryRun": True,
                "SnapshotId": helper.DRYRUN_SNAPSHOT_ID,
                "Attribute": "productCodes",
            },
        )

    def test_verify_policy_action_describe_regions(self):
        """Assert appropriate calls to verify ec2:DescribeRegions."""
        self.assert_verify_policy_action_success(
            "ec2:DescribeRegions", "describe_regions", func_kwargs={"DryRun": True}
        )

    def test_verify_policy_action_describe_snapshots(self):
        """Assert appropriate calls to verify ec2:describe_snapshots."""
        self.assert_verify_policy_action_success(
            "ec2:DescribeSnapshots", "describe_snapshots", func_kwargs={"DryRun": True}
        )

    def test_verify_policy_action_modify_snapshot_attribute(self):
        """Assert appropriate calls to verify ec2:ModifySnapshotAttribute."""
        self.assert_verify_policy_action_success(
            "ec2:ModifySnapshotAttribute",
            "modify_snapshot_attribute",
            func_kwargs={
                "SnapshotId": helper.DRYRUN_SNAPSHOT_ID,
                "DryRun": True,
                "Attribute": "createVolumePermission",
                "OperationType": "add",
            },
        )

    def test_verify_policy_action_copy_image(self):
        """Assert appropriate calls to verify ec2:CopyImage."""
        with patch.object(helper, "uuid") as mock_uuid:
            self.assert_verify_policy_action_success(
                "ec2:CopyImage",
                "copy_image",
                func_kwargs={
                    "Name": f"{mock_uuid.uuid4.return_value}",
                    "DryRun": True,
                    "SourceImageId": helper.DRYRUN_IMAGE_ID,
                    "SourceRegion": helper.DRYRUN_IMAGE_REGION,
                },
            )

    def test_verify_policy_action_create_tags(self):
        """Assert appropriate calls to verify ec2:CreateTags."""
        self.assert_verify_policy_action_success(
            "ec2:CreateTags",
            "create_tags",
            func_kwargs={
                "DryRun": True,
                "Resources": [helper.DRYRUN_IMAGE_ID],
                "Tags": [{"Key": "Example", "Value": "Hello world",},],
            },
        )

    def test_verify_policy_action_unknown(self):
        """Assert trying to verify an unknown action returns False."""
        mock_session = Mock()
        bogus_action = str(uuid.uuid4())
        result = helper._verify_policy_action(mock_session, bogus_action)
        self.assertFalse(result)

    def test_verify_policy_action_create_trail(self):
        """Assert appropriate calls to verify cloudtrail:create_trail."""
        self.assert_verify_policy_action_success(
            "cloudtrail:CreateTrail", "create_trail"
        )

    def test_verify_policy_action_update_trail(self):
        """Assert appropriate calls to verify cloudtrail:update_trail."""
        self.assert_verify_policy_action_success(
            "cloudtrail:UpdateTrail", "update_trail"
        )

    def test_verify_policy_action_describe_trails(self):
        """Assert appropriate calls to verify cloudtrail:describe_trails."""
        self.assert_verify_policy_action_success(
            "cloudtrail:DescribeTrails", "describe_trails"
        )

    def test_verify_policy_action_put_event_selectors(self):
        """Assert calls to verify cloudtrail:put_event_selectors."""
        self.assert_verify_policy_action_success(
            "cloudtrail:PutEventSelectors", "put_event_selectors"
        )

    def test_verify_policy_action_start_logging(self):
        """Assert appropriate calls to verify cloudtrail:start_logging."""
        self.assert_verify_policy_action_success(
            "cloudtrail:StartLogging", "start_logging"
        )

    def test_verify_account_access_failure_unauthorized(self):
        """Assert that account access fails for an unauthorized operation."""
        action = "ec2:DescribeSnapshots"
        function_name = "describe_snapshots"

        mock_function = Mock()
        mock_function.side_effect = ClientError(
            error_response={"Error": {"Code": "UnauthorizedOperation"}},
            operation_name=action,
        )
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_client.attach_mock(mock_function, function_name)

        result = helper._verify_policy_action(mock_session, action)
        self.assertFalse(result)

    def test_verify_account_access_failure_unknown_reason(self):
        """Assert that account access fails for an unknown reason."""
        action = "ec2:DescribeSnapshots"
        function_name = "describe_snapshots"

        mock_function = Mock()
        mock_function.side_effect = ClientError(
            error_response={"Error": {"Code": "itisamystery.gif"}},
            operation_name=action,
        )
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_client.attach_mock(mock_function, function_name)

        with self.assertRaises(ClientError):
            helper._verify_policy_action(mock_session, action)

    @patch("util.aws.helper.boto3.client")
    def test_get_region_from_availability_zone(self, mock_client):
        """Assert that the proper region is returned for an AZ."""
        expected_region = test_helper.get_random_region()
        zone = test_helper.generate_dummy_availability_zone(expected_region)

        az_response = {
            "AvailabilityZones": [
                {"State": "available", "RegionName": expected_region, "ZoneName": zone}
            ]
        }

        mock_desc = mock_client.return_value.describe_availability_zones
        mock_desc.return_value = az_response

        actual_region = helper.get_region_from_availability_zone(zone)
        self.assertEqual(expected_region, actual_region)
