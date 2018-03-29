"""Collection of tests for custom DRF validators in the account app."""
import re
import uuid

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from account import AWS_PROVIDER_STRING
from account.validators import validate_cloud_provider_account_id
from util.tests.helper import generate_dummy_aws_account_id


class ValidatorsTest(TestCase):
    """Validators module tests."""

    def test_validate_cloud_provider_account_id_aws_okay(self):
        """Assert validator works for valid AWS account ID."""
        input_data = {
            'cloud_provider': AWS_PROVIDER_STRING,
            'cloud_account_id': generate_dummy_aws_account_id(),
        }
        output_data = validate_cloud_provider_account_id(input_data)
        self.assertDictEqual(output_data, input_data)
        self.assertIsInstance(output_data['cloud_account_id'], str)
        self.assertIsNotNone(re.match(r'\d{12}',
                                      output_data['cloud_account_id']))

    def test_validate_cloud_provider_account_id_aws_bad_number(self):
        """Assert validator reports error for invalid AWS account ID."""
        input_data = {
            'cloud_provider': AWS_PROVIDER_STRING,
            'cloud_account_id': str(uuid.uuid4()),
        }
        with self.assertRaises(ValidationError):
            validate_cloud_provider_account_id(input_data)

    def test_validate_cloud_provider_account_id_not_special(self):
        """Assert validator passes through if no cloud logic is triggered."""
        input_data = {
            'cloud_provider': 'FOO',
            'cloud_account_id': str(uuid.uuid4()),
        }
        output_data = validate_cloud_provider_account_id(input_data)
        self.assertDictEqual(output_data, input_data)
