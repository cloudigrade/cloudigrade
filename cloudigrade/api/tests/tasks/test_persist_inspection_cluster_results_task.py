"""Collection of tests for tasks.persist_inspection_cluster_results_task."""
import json
import uuid
from unittest.mock import patch

from django.test import TestCase

from api import tasks
from util.tests import helper as util_helper


class PersistInspectionClusterResultsTaskTest(TestCase):
    """Celery task 'persist_inspection_cluster_results_task' test cases."""

    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    @patch('api.tasks.persist_aws_inspection_cluster_results')
    def test_persist_inspect_results_no_messages(
        self, mock_persist, mock_scale_down, _, mock_receive
    ):
        """Assert empty yield results are properly ignored."""
        mock_receive.return_value = []
        tasks.persist_inspection_cluster_results_task()
        mock_persist.assert_not_called()
        mock_scale_down.assert_not_called()

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    @patch('api.tasks.persist_aws_inspection_cluster_results')
    def test_persist_inspect_results_task_aws_success(
        self, mock_persist, mock_scale_down, _, mock_receive, mock_delete
    ):
        """Assert that a valid message is correctly handled and deleted."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        body_dict = {
            'cloud': 'aws',
            'images': {
                'ami-12345': {
                    'rhel_found': False,
                    'rhel_version': None,
                    'syspurpose': None,
                    'drive': {
                        'partition': {
                            'facts': [
                                {
                                    'release_file': '/centos-release',
                                    'release_file_contents': 'CentOS\n',
                                    'rhel_found': False,
                                }
                            ]
                        }
                    },
                }
            },
        }
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle
        )
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_persist.assert_called_once_with(body_dict)
        mock_delete.assert_called_once()
        mock_scale_down.delay.assert_called_once()
        self.assertIn(sqs_message, s)
        self.assertEqual([], f)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    @patch('api.tasks.persist_aws_inspection_cluster_results')
    def test_persist_inspect_results_unknown_cloud(
        self, mock_persist, mock_scale_down, _, mock_receive, mock_delete
    ):
        """Assert message is not deleted for unknown cloud."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        body_dict = {'cloud': 'unknown'}
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle
        )
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_persist.assert_not_called()
        mock_delete.assert_not_called()
        mock_scale_down.delay.assert_called_once()
        self.assertEqual([], s)
        self.assertIn(sqs_message, f)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    def test_persist_inspect_results_aws_cloud_no_images(
        self, mock_scale_down, _, mock_receive, mock_delete
    ):
        """Assert message is not deleted if it is missing images."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        body_dict = {'cloud': 'aws'}
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle
        )
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_delete.assert_not_called()
        mock_scale_down.delay.assert_called_once()
        self.assertEqual([], s)
        self.assertIn(sqs_message, f)

    @patch('api.tasks.aws.delete_messages_from_queue')
    @patch('api.tasks.aws.yield_messages_from_queue')
    @patch('api.tasks.aws.get_sqs_queue_url')
    @patch('api.tasks.scale_down_cluster')
    def test_persist_inspect_results_aws_cloud_image_not_found(
        self, mock_scale_down, _, mock_receive, mock_delete
    ):
        """
        Assert message is still deleted when our image is not found.

        See also: test_persist_aws_inspection_cluster_results_our_model_is_gone
        """
        body_dict = {'cloud': 'aws', 'images': {'fake_image': {}}}
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(body_dict), receipt_handle
        )
        mock_receive.return_value = [sqs_message]

        s, f = tasks.persist_inspection_cluster_results_task()

        mock_delete.assert_called_once()
        mock_scale_down.delay.assert_called_once()
        self.assertIn(sqs_message, s)
        self.assertEqual([], f)
