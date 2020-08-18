"""Collection of tests for aws.tasks.cloudtrail.scale_up_inspection_cluster."""
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from api.clouds.aws import tasks


class ScaleUpInspectionClusterTest(TestCase):
    """Celery task 'scale_up_inspection_cluster' test cases."""

    def setUp(self):
        """Set up expected ready_volumes queue name."""
        self.ready_volumes_queue_name = "{0}ready_volumes".format(
            settings.AWS_NAME_PREFIX
        )

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_scale_up_inspection_cluster_success(
        self, mock_aws, mock_run_inspection_cluster
    ):
        """Assert successful scaling with empty cluster and queued messages."""
        messages = [Mock()]
        mock_aws.is_scaled_down.return_value = True, dict()
        mock_aws.read_messages_from_queue.return_value = messages

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.read_messages_from_queue.assert_called_once_with(
            self.ready_volumes_queue_name, settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE,
        )
        mock_aws.scale_up.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_run_inspection_cluster.delay.assert_called_once_with(messages)
        mock_aws.add_messages_to_queue.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_scale_up_inspection_cluster_aborts_when_not_scaled_down(
        self, mock_aws, mock_run_inspection_cluster
    ):
        """Assert scale up aborts when not scaled down."""
        mock_aws.is_scaled_down.return_value = False, {"Instances": [Mock()]}

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_not_called()
        mock_aws.read_messages_from_queue.assert_not_called()
        mock_run_inspection_cluster.delay.assert_not_called()
        mock_aws.add_messages_to_queue.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_scale_up_inspection_cluster_aborts_when_no_messages(
        self, mock_aws, mock_run_inspection_cluster
    ):
        """Assert scale up aborts when not scaled down."""
        mock_aws.is_scaled_down.return_value = True, dict()
        mock_aws.read_messages_from_queue.return_value = []

        tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_not_called()
        mock_aws.read_messages_from_queue.assert_called_once_with(
            self.ready_volumes_queue_name, settings.HOUNDIGRADE_AWS_VOLUME_BATCH_SIZE,
        )
        mock_run_inspection_cluster.delay.assert_not_called()
        mock_aws.add_messages_to_queue.assert_not_called()

    @patch("api.clouds.aws.tasks.inspection.run_inspection_cluster")
    @patch("api.clouds.aws.tasks.inspection.aws")
    def test_scale_up_inspection_cluster_requeues_on_aws_error(
        self, mock_aws, mock_run_inspection_cluster
    ):
        """Assert messages requeue when scale_up encounters AWS exception."""
        messages = [Mock()]
        mock_aws.is_scaled_down.return_value = True, dict()
        mock_aws.read_messages_from_queue.return_value = messages
        mock_aws.scale_up.side_effect = ClientError({}, Mock())

        with self.assertRaises(RuntimeError):
            tasks.scale_up_inspection_cluster()

        mock_aws.is_scaled_down.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.scale_up.assert_called_once_with(
            settings.HOUNDIGRADE_AWS_AUTOSCALING_GROUP_NAME
        )
        mock_aws.add_messages_to_queue.assert_called_once_with(
            self.ready_volumes_queue_name, messages
        )
        mock_run_inspection_cluster.delay.assert_not_called()
