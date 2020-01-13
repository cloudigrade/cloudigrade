"""Collection of tests for tasks.remove_snapshot_ownership."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api.tasks import remove_snapshot_ownership
from util.tests import helper as util_helper


class RemoveSnapshotOwnershipTest(TestCase):
    """Celery task 'remove_snapshot_ownership' test cases."""

    @patch("api.tasks.boto3")
    @patch("api.tasks.aws")
    def test_remove_snapshot_ownership_success(self, mock_aws, mock_boto3):
        """Assert that the remove snapshot ownership task succeeds."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_customer_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_customer_snapshot = util_helper.generate_mock_snapshot(
            mock_customer_snapshot_id
        )
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy = util_helper.generate_mock_snapshot(mock_snapshot_copy_id)
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot_copy

        mock_aws.check_snapshot_state.return_value = None
        mock_aws.get_snapshot.return_value = mock_customer_snapshot

        mock_aws.get_region_from_availability_zone.return_value = region

        remove_snapshot_ownership(
            mock_arn, mock_customer_snapshot_id, region, mock_snapshot_copy_id
        )

        mock_aws.remove_snapshot_ownership.assert_called_with(mock_customer_snapshot)

    @patch("api.tasks.boto3")
    @patch("api.tasks.aws")
    def test_remove_snapshot_ownership_no_copy_snapshot(self, mock_aws, mock_boto3):
        """Assert remove snapshot ownership task succeeds with missing copy."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_customer_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_customer_snapshot = util_helper.generate_mock_snapshot(
            mock_customer_snapshot_id
        )
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy = util_helper.generate_mock_snapshot(mock_snapshot_copy_id)
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        client_error = ClientError(
            error_response={"Error": {"Code": "InvalidSnapshot.NotFound"}},
            operation_name=Mock(),
        )

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot_copy
        resource.Snapshot.side_effect = client_error

        mock_aws.check_snapshot_state.return_value = None
        mock_aws.get_snapshot.return_value = mock_customer_snapshot

        mock_aws.get_region_from_availability_zone.return_value = region

        remove_snapshot_ownership(
            mock_arn, mock_customer_snapshot_id, region, mock_snapshot_copy_id
        )

        mock_aws.remove_snapshot_ownership.assert_called_with(mock_customer_snapshot)

    @patch("api.tasks.boto3")
    @patch("api.tasks.aws")
    def test_remove_snapshot_ownership_unexpected_error(self, mock_aws, mock_boto3):
        """Assert remove snapshot ownership fails due to unexpected error."""
        mock_arn = util_helper.generate_dummy_arn()
        mock_customer_snapshot_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        client_error = ClientError(
            error_response={"Error": {"Code": "InvalidSnapshot.Unknown"}},
            operation_name=Mock(),
        )

        resource = mock_boto3.resource.return_value
        resource.Snapshot.side_effect = client_error

        with self.assertRaises(RuntimeError):
            remove_snapshot_ownership(
                mock_arn, mock_customer_snapshot_id, region, mock_snapshot_copy_id,
            )

        mock_aws.remove_snapshot_ownership.assert_not_called()
