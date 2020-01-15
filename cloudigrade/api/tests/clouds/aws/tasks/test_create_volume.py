"""Collection of tests for tasks.create_volume."""
from unittest.mock import patch

from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase

from api.clouds.aws import tasks
from util.exceptions import AwsSnapshotError, SnapshotNotReadyException
from util.tests import helper as util_helper


class CreateVolumeTest(TestCase):
    """Celery task 'create_volume' test cases."""

    @patch("api.clouds.aws.tasks.aws")
    def test_create_volume_success(self, mock_aws):
        """Assert that the volume create task succeeds."""
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_id = util_helper.generate_dummy_snapshot_id()
        zone = settings.HOUNDIGRADE_AWS_AVAILABILITY_ZONE
        region = zone[:-1]

        mock_volume = util_helper.generate_mock_volume()
        mock_aws.create_volume.return_value = mock_volume.id
        mock_aws.get_region_from_availability_zone.return_value = region

        with patch.object(tasks, "enqueue_ready_volume") as mock_enqueue:
            with patch.object(tasks, "delete_snapshot") as mock_delete_snapshot:
                tasks.create_volume(ami_id, snapshot_id)
                mock_enqueue.delay.assert_called_with(ami_id, mock_volume.id, region)
                mock_delete_snapshot.delay.assert_called_with(
                    snapshot_id, mock_volume.id, region
                )

        mock_aws.create_volume.assert_called_with(snapshot_id, zone)

    @patch("api.clouds.aws.tasks.aws")
    def test_create_volume_retry_on_snapshot_not_ready(self, mock_aws):
        """Assert that the volume create task retries."""
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.create_volume.side_effect = SnapshotNotReadyException(snapshot_id)

        with patch.object(tasks, "enqueue_ready_volume") as mock_enqueue, patch.object(
            tasks.create_volume, "retry"
        ) as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                tasks.create_volume(ami_id, snapshot_id)
            self.assertTrue(mock_retry.called)
            mock_enqueue.delay.assert_not_called()

    @patch("api.clouds.aws.tasks.aws")
    def test_create_volume_abort_on_snapshot_error(self, mock_aws):
        """Assert that the volume create task does not retry on error."""
        ami_id = util_helper.generate_dummy_image_id()
        snapshot_id = util_helper.generate_dummy_snapshot_id()

        mock_aws.create_volume.side_effect = AwsSnapshotError()

        with patch.object(tasks, "enqueue_ready_volume") as mock_enqueue, patch.object(
            tasks.create_volume, "retry"
        ) as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(AwsSnapshotError):
                tasks.create_volume(ami_id, snapshot_id)
            mock_retry.assert_not_called()
            mock_enqueue.delay.assert_not_called()
