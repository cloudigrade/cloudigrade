"""Collection of tests for ``util.aws`` module."""
import uuid
from unittest.mock import patch

import faker
from django.test import TestCase

from util import aws
from util.tests import helper


class UtilAwsTest(TestCase):
    """AWS utility functions test case."""

    def test_extract_account_id_from_arn(self):
        """Assert successful account ID extraction from a well-formed ARN."""
        mock_account_id = helper.generate_dummy_aws_account_id()
        mock_arn = helper.generate_dummy_arn(mock_account_id)
        extracted_account_id = aws.extract_account_id_from_arn(mock_arn)
        self.assertEqual(mock_account_id, extracted_account_id)

    def test_error_extract_account_id_from_invalid_arn(self):
        """Assert error in account ID extraction from a badly-formed ARN."""
        mock_arn = faker.Faker().text()
        with self.assertRaises(Exception):  # TODO more specific exceptions
            aws.extract_account_id_from_arn(mock_arn)

    def test_get_regions_with_no_args(self):
        """Assert get_regions with no args returns expected regions."""
        mock_regions = [
            f'region-{uuid.uuid4()}',
            f'region-{uuid.uuid4()}',
        ]

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            mock_session.get_available_regions.return_value = mock_regions
            actual_regions = aws.get_regions()
            self.assertTrue(mock_session.get_available_regions.called)
            mock_session.get_available_regions.assert_called_with('ec2')
        self.assertListEqual(mock_regions, actual_regions)

    def test_get_regions_with_custom_service(self):
        """Assert get_regions with service name returns expected regions."""
        mock_regions = [
            f'region-{uuid.uuid4()}',
            f'region-{uuid.uuid4()}',
        ]

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_session = mock_boto3.Session.return_value
            mock_session.get_available_regions.return_value = mock_regions
            actual_regions = aws.get_regions('tng')
            self.assertTrue(mock_session.get_available_regions.called)
            mock_session.get_available_regions.assert_called_with('tng')
        self.assertListEqual(mock_regions, actual_regions)

    def test_get_credentials_for_arn(self):
        """Assert get_credentials_for_arn returns credentials dict."""
        mock_arn = helper.generate_dummy_arn()
        mock_role = {
            'Credentials': {
                'AccessKeyId': str(uuid.uuid4()),
                'SecretAccessKey': str(uuid.uuid4()),
                'SessionToken': str(uuid.uuid4()),
            },
            'foo': 'bar',
        }

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_client = mock_boto3.client.return_value
            mock_assume_role = mock_client.assume_role
            mock_assume_role.return_value = mock_role

            actual_credentials = aws.get_credentials_for_arn(mock_arn)

            mock_boto3.client.assert_called_with('sts')
            mock_assume_role.assert_called_with(RoleArn=mock_arn,
                                                RoleSessionName='temp-session')

        self.assertDictEqual(mock_role['Credentials'], actual_credentials)

    def test_get_running_instances(self):
        """Assert we get instances in a dict with regions for keys."""
        mock_arn = helper.generate_dummy_arn()
        mock_regions = [f'region-{uuid.uuid4()}']
        mock_credentials = {
            'AccessKeyId': str(uuid.uuid4()),
            'SecretAccessKey': str(uuid.uuid4()),
            'SessionToken': str(uuid.uuid4()),
        }
        mock_instance_id = str(uuid.uuid4())
        mock_described = {
            'Reservations': [
                {
                    'Instances': [
                        {
                            'InstanceId': mock_instance_id,
                        },
                    ],
                },
            ],
        }
        expected_found = {
            mock_regions[0]: [mock_instance_id]
        }

        with patch.object(aws, 'get_credentials_for_arn') as mock_get_creds, \
                patch.object(aws, 'get_regions') as mock_get_regions, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_get_creds.return_value = mock_credentials
            mock_get_regions.return_value = mock_regions
            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_client.describe_instances.return_value = mock_described

            actual_found = aws.get_running_instances(mock_arn)

        self.assertDictEqual(expected_found, actual_found)
