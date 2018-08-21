"""Collection of tests for ``analyzer.tests.helper`` module.

Because even test helpers should be tested!
"""
import json
import uuid

import faker
from django.test import TestCase

from analyzer.tests import helper as analyzer_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class AnalyzerHelperTest(TestCase):
    """Analyzer test helper module tests."""

    def test_generate_mock_cloudtrail_sqs_message_all_args(self):
        """Test generate_mock_cloudtrail_sqs_message with all arguments."""
        bucket_name = _faker.bs()
        object_key = _faker.file_path()
        receipt_handle = str(uuid.uuid4())
        message_id = str(uuid.uuid4())

        message = analyzer_helper.generate_mock_cloudtrail_sqs_message(
            bucket_name=bucket_name, object_key=object_key,
            receipt_handle=receipt_handle, message_id=message_id)

        self.assertEqual(message.Id, message_id)
        self.assertEqual(message.ReceiptHandle, receipt_handle)
        s3_data = json.loads(message.body)['Records'][0]['s3']
        self.assertEqual(s3_data['bucket']['name'], bucket_name)
        self.assertEqual(s3_data['object']['key'], object_key)

    def test_generate_mock_cloudtrail_sqs_message_no_args(self):
        """Test generate_mock_cloudtrail_sqs_message with no arguments."""
        message = analyzer_helper.generate_mock_cloudtrail_sqs_message()
        self.assertIsNotNone(message.Id)
        self.assertIsNotNone(message.ReceiptHandle)
        s3_data = json.loads(message.body)['Records'][0]['s3']
        self.assertIsNotNone(s3_data['bucket']['name'])
        self.assertIsNotNone(s3_data['object']['key'])

    def test_generate_cloudtrail_log_record_all_args(self):
        """Test generate_cloudtrail_log_record with all arguments."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        instance_ids = [
            util_helper.generate_dummy_instance_id(),
            util_helper.generate_dummy_instance_id(),
        ]
        event_name = _faker.bs()
        event_time = util_helper.utc_dt(1999, 12, 25)
        record = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id, instance_ids, event_name, event_time)

        self.assertEqual(record['userIdentity']['accountId'], aws_account_id)
        self.assertIsNotNone(record['awsRegion'])
        self.assertIsNotNone(record['eventName'])
        items = record['responseElements']['instancesSet']['items']
        actual_instance_ids = set([item['instanceId'] for item in items])
        self.assertEqual(set(instance_ids), actual_instance_ids)

    def test_generate_cloudtrail_log_record_minimum_args(self):
        """Test generate_cloudtrail_log_record with minimum arguments."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        instance_ids = [
            util_helper.generate_dummy_instance_id(),
            util_helper.generate_dummy_instance_id(),
        ]
        record = analyzer_helper.generate_cloudtrail_log_record(
            aws_account_id, instance_ids)
        self.assertEqual(record['userIdentity']['accountId'], aws_account_id)
        self.assertIsNotNone(record['awsRegion'])
        self.assertIsNotNone(record['eventName'])
        items = record['responseElements']['instancesSet']['items']
        actual_instance_ids = set([item['instanceId'] for item in items])
        self.assertEqual(set(instance_ids), actual_instance_ids)
