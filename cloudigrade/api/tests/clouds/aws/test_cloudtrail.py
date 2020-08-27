"""Collection of tests for the cloudtrail module."""
from django.test import TestCase

from api.clouds.aws import cloudtrail
from api.tests import helper as analyzer_helper
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class ExtractEC2InstanceEventsTest(TestCase):
    """Extract EC2 instance events test case."""

    def setUp(self):
        """Set up an AwsCloudAccount for relevant events."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = api_helper.generate_cloud_account(
            aws_account_id=self.aws_account_id,
            user=self.user,
            created_at=util_helper.utc_dt(2017, 12, 1, 0, 0, 0),
        )

    def test_extract_ec2_instance_events_invalid_event(self):
        """Assert that no events are extracted from an invalid record."""
        record = {"potato": "gems"}
        expected = []
        extracted = cloudtrail.extract_ec2_instance_events(record)
        self.assertEqual(extracted, expected)

    def test_extract_ec2_instance_events_missing_instancetype(self):
        """Assert that no events are extracted if instance type is missing."""
        record = analyzer_helper.generate_cloudtrail_record(
            self.aws_account_id, "ModifyInstanceAttribute"
        )
        expected = []
        extracted = cloudtrail.extract_ec2_instance_events(record)
        self.assertEqual(extracted, expected)
