"""Collection of tests for aws.tasks.cloudtrail.enqueue_ready_volume."""
import random
from unittest.mock import patch

from celery.exceptions import Retry
from django.conf import settings
from django.test import TestCase

from api.clouds.aws.tasks import enqueue_ready_volume
from util.exceptions import AwsVolumeError, AwsVolumeNotReadyError
from util.tests import helper as util_helper


class EnqueueReadyVolumeTest(TestCase):
    """Celery task 'enqueue_ready_volume' test cases."""

    def setUp(self):
        """Set up expected ready_volumes queue name."""
        self.ready_volumes_queue_name = "{0}ready_volumes".format(
            settings.AWS_NAME_PREFIX
        )

    @patch("api.clouds.aws.tasks.imageprep.add_messages_to_queue")
    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_enqueue_ready_volume_success(self, mock_aws, mock_queue):
        """Assert that volumes are enqueued when ready."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id, state="available"
        )
        region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume

        messages = [{"ami_id": ami_id, "volume_id": volume_id}]
        enqueue_ready_volume(ami_id, volume_id, region)

        mock_queue.assert_called_with(self.ready_volumes_queue_name, messages)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_enqueue_ready_volume_error(self, mock_aws):
        """Assert that an error is raised on bad volume state."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id,
            state=random.choice(("in-use", "deleting", "deleted", "error")),
        )
        region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        mock_aws.check_volume_state.side_effect = AwsVolumeError()

        with self.assertRaises(AwsVolumeError):
            enqueue_ready_volume(ami_id, volume_id, region)

    @patch("api.clouds.aws.tasks.imageprep.aws")
    def test_enqueue_ready_volume_retry(self, mock_aws):
        """Assert that the task retries when volume is not available."""
        ami_id = util_helper.generate_dummy_image_id()
        volume_id = util_helper.generate_dummy_volume_id()
        mock_volume = util_helper.generate_mock_volume(
            volume_id=volume_id, state="creating"
        )
        region = mock_volume.zone[:-1]

        mock_aws.get_volume.return_value = mock_volume
        mock_aws.check_volume_state.side_effect = AwsVolumeNotReadyError()

        with patch.object(enqueue_ready_volume, "retry") as mock_retry:
            mock_retry.side_effect = Retry()
            with self.assertRaises(Retry):
                enqueue_ready_volume(ami_id, volume_id, region)
