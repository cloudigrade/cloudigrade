"""Collection of tests for aws.tasks.cloudtrail.delete_snapshot."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api.clouds.aws.tasks import delete_snapshot
from api.models import MachineImage
from api.tests import helper as account_helper
from util.tests import helper as util_helper


class DeleteSnapshotTest(TestCase):
    """Celery task 'delete_snapshot' test cases."""

    @patch("api.clouds.aws.tasks.imageprep.AwsMachineImage")
    @patch("api.clouds.aws.tasks.imageprep.boto3")
    def test_delete_snapshot_success(self, mock_boto3, mock_ami):
        """Assert that the delete snapshot succeeds."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        mock_image = account_helper.generate_image(
            ec2_ami_id=mock_ami_id, status=MachineImage.INSPECTED
        )
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_region = util_helper.get_random_region()

        mock_ami_get = mock_ami.objects.get
        mock_ami_get.return_value.machine_image.get.return_value = mock_image
        mock_ec2_client = mock_boto3.resource
        mock_snapshot = mock_ec2_client.return_value.Snapshot

        delete_snapshot(mock_snapshot_copy_id, mock_ami_id, mock_region)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_snapshot.assert_called_once_with(mock_snapshot_copy_id)
        mock_snapshot.return_value.delete.assert_called_once()

    @patch("api.clouds.aws.tasks.imageprep.delete_snapshot.apply_async")
    @patch("api.clouds.aws.tasks.imageprep.AwsMachineImage")
    @patch("api.clouds.aws.tasks.imageprep.boto3")
    def test_delete_snapshot_retry(self, mock_boto3, mock_ami, mock_async):
        """Assert that the delete snapshot retries."""
        mock_ami_id = util_helper.generate_dummy_image_id()
        mock_image = account_helper.generate_image(
            ec2_ami_id=mock_ami_id, status=MachineImage.INSPECTING
        )
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_region = util_helper.get_random_region()

        mock_ami_get = mock_ami.objects.get
        mock_ami_get.return_value.machine_image.get.return_value = mock_image
        mock_ec2_client = mock_boto3.resource
        mock_snapshot = mock_ec2_client.return_value.Snapshot

        delete_snapshot(mock_snapshot_copy_id, mock_ami_id, mock_region)

        mock_async.assert_called_once_with(
            args=[mock_snapshot_copy_id, mock_ami_id, mock_region],
            countdown=settings.INSPECTION_SNAPSHOT_CLEAN_UP_RETRY_DELAY,
        )
        mock_snapshot.return_value.delete.assert_not_called()

    @patch("api.clouds.aws.tasks.imageprep.boto3")
    def test_delete_snapshot_ami_deleted(self, mock_boto3):
        """Assert that the delete snapshot cleans up orphaned snapshots."""
        mock_ami_id = util_helper.generate_dummy_image_id()
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_region = util_helper.get_random_region()

        mock_ec2_client = mock_boto3.resource
        mock_snapshot = mock_ec2_client.return_value.Snapshot

        delete_snapshot(mock_snapshot_copy_id, mock_ami_id, mock_region)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_snapshot.assert_called_once_with(mock_snapshot_copy_id)
        mock_snapshot.return_value.delete.assert_called_once()

    @patch("api.clouds.aws.tasks.imageprep.AwsMachineImage")
    @patch("api.clouds.aws.tasks.imageprep.boto3")
    def test_delete_snapshot_missing(self, mock_boto3, mock_ami):
        """Assert that the delete snapshot handles already deleted snapshots."""
        mock_ami_id = util_helper.generate_dummy_image_id()

        mock_image = account_helper.generate_image(
            ec2_ami_id=mock_ami_id, status=MachineImage.INSPECTED
        )
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_region = util_helper.get_random_region()

        client_error = ClientError(
            error_response={"Error": {"Code": "InvalidSnapshot.NotFound"}},
            operation_name=Mock(),
        )

        mock_ami_get = mock_ami.objects.get
        mock_ami_get.return_value.machine_image.get.return_value = mock_image
        mock_ec2_client = mock_boto3.resource
        mock_snapshot = mock_ec2_client.return_value.Snapshot
        mock_snapshot.return_value.delete.side_effect = client_error

        delete_snapshot(mock_snapshot_copy_id, mock_ami_id, mock_region)

        mock_ec2_client.assert_called_once_with("ec2")
        mock_snapshot.assert_called_once_with(mock_snapshot_copy_id)
        mock_snapshot.return_value.delete.assert_called_once()
