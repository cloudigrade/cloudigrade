"""Collection of tests for tasks.delete_snapshot."""
from unittest.mock import patch

from django.test import TestCase

from api.clouds.aws.tasks import delete_snapshot
from util.tests import helper as util_helper


class DeleteSnapshotTest(TestCase):
    """Celery task 'delete_snapshot' test cases."""

    @patch("api.clouds.aws.tasks.boto3")
    @patch("api.clouds.aws.tasks.aws")
    def test_delete_snapshot_success(self, mock_aws, mock_boto3):
        """Assert that the delete snapshot succeeds."""
        mock_snapshot_copy_id = util_helper.generate_dummy_snapshot_id()
        mock_snapshot_copy = util_helper.generate_mock_snapshot(mock_snapshot_copy_id)

        resource = mock_boto3.resource.return_value
        resource.Snapshot.return_value = mock_snapshot_copy

        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id, state="available"
        )
        volume_region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        mock_aws.check_volume_state.return_value = None

        delete_snapshot(mock_snapshot_copy_id, volume_id, volume_region)
