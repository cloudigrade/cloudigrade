"""Collection of tests for ``util.tests.helper`` module.

Because even test helpers should be tested!
"""
from django.test import TestCase

from util import aws
from util.tests import helper


class UtilHelperTest(TestCase):
    """Test helper functions test case."""

    def test_generate_dummy_aws_account_id(self):
        """Assert generation of an appropriate AWS Account ID."""
        account_id = helper.generate_dummy_aws_account_id()
        self.assertLess(account_id, helper.MAX_AWS_ACCOUNT_ID)
        self.assertGreater(account_id, 0)

    def test_generate_dummy_arn_random_account_id(self):
        """Assert generation of an ARN without a specified account ID."""
        arn = helper.generate_dummy_arn()
        account_id = aws.extract_account_id_from_arn(arn)
        self.assertIn(str(account_id), arn)

    def test_generate_dummy_arn_given_account_id(self):
        """Assert generation of an ARN with a specified account ID."""
        account_id = 123456789
        arn = helper.generate_dummy_arn(account_id)
        self.assertIn(str(account_id), arn)
