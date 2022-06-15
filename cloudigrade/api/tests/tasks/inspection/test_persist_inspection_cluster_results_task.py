"""Collection of tests for tasks.inspection.persist_inspection_cluster_results_task."""
import json
import uuid
from unittest.mock import patch

import faker
from django.test import TestCase

from api.tasks import inspection
from util.tests import helper as util_helper

_faker = faker.Faker()


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

    @patch("util.aws.delete_messages_from_queue")
    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection.persist_aws_inspection_cluster_results")
    def test_persist_inspect_results_s3_testevent_log_and_delete(
        self, mock_persist, _, mock_receive, mock_delete
    ):
        """Assert an s3:TestEvent message is simply logged and deleted."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        message_body = util_helper.generate_dummy_s3_testevent_message()
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, message_body, receipt_handle
        )
        mock_receive.return_value = [sqs_message]
        with self.assertLogs("api.tasks.inspection", level="INFO") as logging_watcher:
            inspection.persist_inspection_cluster_results_task()
        self.assertEqual(
            logging_watcher.records[-2].message,
            f"s3:TestEvent message received: {message_body}",
        )
        self.assertEqual(
            logging_watcher.records[-1].message, "No inspection results found."
        )
        mock_persist.assert_not_called()
        mock_delete.assert_called_once()

    @patch("util.aws.delete_messages_from_queue")
    @patch("util.aws.yield_messages_from_queue")
    @patch("util.aws.get_sqs_queue_url")
    @patch("api.tasks.inspection.persist_aws_inspection_cluster_results")
    def test_persist_inspect_results_mystery_message_logged(
        self, mock_persist, _, mock_receive, mock_delete
    ):
        """Assert mysterious message with no inspection results is simply logged."""
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())
        message_body = f'{{"{_faker.slug()}":"{_faker.slug()}"}}'
        sqs_message = util_helper.generate_mock_sqs_message(
            message_id, message_body, receipt_handle
        )
        mock_receive.return_value = [sqs_message]
        with self.assertLogs("api.tasks.inspection", level="INFO") as logging_watcher:
            inspection.persist_inspection_cluster_results_task()
        self.assertEqual(
            f"No inspection results found for SQS message: {message_body}",
            logging_watcher.records[-2].message,
        )
        self.assertEqual("ERROR", logging_watcher.records[-2].levelname)
        self.assertEqual(
            "No inspection results found.", logging_watcher.records[-1].message
        )
        mock_persist.assert_not_called()
        mock_delete.assert_not_called()

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

    def test_is_s3_testevent_message_true(self):
        """Assert we correctly identify an s3:TestEvent message."""
        message = util_helper.generate_dummy_s3_testevent_message()
        self.assertTrue(inspection._is_s3_testevent_message(message))

    def test_is_s3_testevent_message_false(self):
        """Assert we correctly identify a not-s3:TestEvent message."""
        message = f'{{"Service":"{_faker.slug()}","Event":"{_faker.slug()}"}}'
        self.assertFalse(inspection._is_s3_testevent_message(message))

    def test_is_s3_testevent_message_false_because_exception(self):
        """Assert non-JSON message is not identified as an s3:TestEvent message."""
        message = str(uuid.uuid4())  # Not valid JSON, would internally raise exception.
        self.assertFalse(inspection._is_s3_testevent_message(message))
