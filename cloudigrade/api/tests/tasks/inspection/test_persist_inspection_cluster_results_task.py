"""Collection of tests for tasks.inspection.persist_inspection_cluster_results_task."""
import json
import uuid
from unittest.mock import patch

from django.test import TestCase

from api.tasks import inspection
from util.tests import helper as util_helper


class PersistInspectionClusterResultsTaskTest(TestCase):
    """Celery task 'persist_inspection_cluster_results_task' test cases."""

    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection.persist_aws_inspection_cluster_results")
    def test_persist_inspect_results_no_messages(self, mock_persist, _, mock_receive):
        """Assert empty yield results are properly ignored."""
        mock_receive.return_value = []
        inspection.persist_inspection_cluster_results_task()
        mock_persist.assert_not_called()

    @patch("util.aws.delete_messages_from_queue")
    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection._fetch_inspection_results")
    @patch("api.tasks.inspection.persist_aws_inspection_cluster_results")
    def test_persist_inspect_results_task_aws_success(
        self, mock_persist, mock_fetch_results, _, mock_receive, mock_delete
    ):
        """Assert that a valid message is correctly handled and deleted."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        inspection_dict = {
            "cloud": "aws",
            "images": {
                "ami-12345": {
                    "rhel_found": False,
                    "rhel_version": None,
                    "syspurpose": None,
                    "drive": {
                        "partition": {
                            "facts": [
                                {
                                    "release_file": "/centos-release",
                                    "release_file_contents": "CentOS\n",
                                    "rhel_found": False,
                                }
                            ]
                        }
                    },
                }
            },
        }
        mock_fetch_results.return_value = [inspection_dict]

        sqs_message = util_helper.generate_mock_sqs_message(
            message_id,
            json.dumps({"Key": "/InspectionResults/results.json"}),
            receipt_handle,
        )
        mock_receive.return_value = [sqs_message]

        s, f = inspection.persist_inspection_cluster_results_task()

        mock_persist.assert_called_once_with(inspection_dict)
        mock_delete.assert_called_once()
        self.assertEqual(sqs_message.message_id, s[0]["message_id"])
        self.assertEqual(sqs_message.body, s[0]["body"])
        self.assertEqual([], f)

    @patch("util.aws.delete_messages_from_queue")
    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection._fetch_inspection_results")
    @patch("api.tasks.inspection.persist_aws_inspection_cluster_results")
    def test_persist_inspect_results_unknown_cloud(
        self, mock_persist, mock_fetch_results, _, mock_receive, mock_delete
    ):
        """Assert message is not deleted for unknown cloud."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        inspection_dict = {"cloud": "unknown"}
        mock_fetch_results.return_value = [inspection_dict]
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id,
            json.dumps({"Key": "/InspectionResults/results.json"}),
            receipt_handle,
        )
        mock_receive.return_value = [sqs_message]

        s, f = inspection.persist_inspection_cluster_results_task()

        mock_persist.assert_not_called()
        mock_delete.assert_not_called()
        self.assertEqual([], s)
        self.assertEqual(sqs_message.message_id, f[0]["message_id"])
        self.assertEqual(sqs_message.body, f[0]["body"])

    @patch("util.aws.delete_messages_from_queue")
    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection._fetch_inspection_results")
    def test_persist_inspect_results_aws_cloud_no_images(
        self, mock_fetch_results, _, mock_receive, mock_delete
    ):
        """Assert message is not deleted if it is missing images."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        inspection_dict = {"cloud": "aws"}
        mock_fetch_results.return_value = [inspection_dict]
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(inspection_dict), receipt_handle
        )
        mock_receive.return_value = [sqs_message]

        s, f = inspection.persist_inspection_cluster_results_task()

        mock_delete.assert_not_called()
        self.assertEqual([], s)
        self.assertEqual(sqs_message.message_id, f[0]["message_id"])
        self.assertEqual(sqs_message.body, f[0]["body"])

    @patch("util.aws.delete_messages_from_queue")
    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection._fetch_inspection_results")
    def test_persist_inspect_results_aws_cloud_image_not_found(
        self, mock_fetch_results, _, mock_receive, mock_delete
    ):
        """
        Assert message is still deleted when our image is not found.

        See also: test_persist_aws_inspection_cluster_results_our_model_is_gone
        """
        inspection_dict = {"cloud": "aws", "images": {"fake_image": {}}}
        mock_fetch_results.return_value = [inspection_dict]
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, json.dumps(inspection_dict), receipt_handle
        )
        mock_receive.return_value = [sqs_message]

        s, f = inspection.persist_inspection_cluster_results_task()

        mock_delete.assert_called_once()
        self.assertEqual(sqs_message.message_id, s[0]["message_id"])
        self.assertEqual(sqs_message.body, s[0]["body"])
        self.assertEqual([], f)

    @patch("api.tasks.inspection.aws")
    def test_fetch_inspection_results_success(self, mock_aws):
        """Assert we correctly fetch results from provided bucket and key."""
        mock_inspection_dict = '{"cloud": "aws"}'
        mock_message = "MockMessage"
        mock_bucket_name = "TestBucket"
        mock_key = "/InspectionResults/results.json"
        mock_extracted_message = {
            "bucket": {"name": mock_bucket_name},
            "object": {"key": mock_key},
        }
        mock_extract_messages = mock_aws.extract_sqs_message
        mock_extract_messages.return_value = [mock_extracted_message]
        mock_get_object = mock_aws.get_object_content_from_s3
        mock_get_object.return_value = mock_inspection_dict

        results = inspection._fetch_inspection_results(mock_message)
        mock_extract_messages.assert_called_once_with(mock_message)
        mock_get_object.assert_called_once_with(mock_bucket_name, mock_key)
        self.assertEqual(json.loads(mock_inspection_dict), results[0])
