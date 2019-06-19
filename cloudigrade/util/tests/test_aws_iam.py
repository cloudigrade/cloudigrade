"""Collection of tests for ``util.aws.sts`` module."""
from unittest.mock import Mock, patch

import faker
from django.test import TestCase

from util import exceptions
from util.aws import AwsArn, iam
from util.tests import helper

_faker = faker.Faker()


class UtilAwsIamTest(TestCase):
    """AWS IAM utility functions test case."""

    @patch('util.aws.iam.get_session_account_id')
    @patch('util.aws.iam._get_primary_account_id')
    def test_get_standard_policy_name_and_arn(
        self, mock_get_primary_account_id, mock_get_session_account_id
    ):
        """Assert get_standard_policy_name_and_arn returns expected values."""
        system_account_id = helper.generate_dummy_aws_account_id()
        customer_account_id = helper.generate_dummy_aws_account_id()

        mock_get_primary_account_id.return_value = system_account_id
        mock_get_session_account_id.return_value = customer_account_id

        mock_session = Mock()
        policy_name, policy_arn = iam.get_standard_policy_name_and_arn(
            mock_session
        )
        mock_get_session_account_id.assert_called_with(mock_session)
        mock_get_primary_account_id.assert_called()

        arn = AwsArn(policy_arn)
        self.assertEqual(arn.account_id, customer_account_id)
        self.assertEqual(arn.service, 'iam')
        self.assertEqual(arn.resource_type, 'policy')
        self.assertIn(str(system_account_id), arn.resource)

    @patch('util.aws.iam.get_standard_policy_name_and_arn')
    def test_ensure_cloudigrade_policy_new(
        self, mock_get_standard_policy_name_and_arn
    ):
        """Assert ensure_cloudigrade_policy creates a policy if none exists."""
        policy_name = _faker.slug()
        policy_arn = helper.generate_dummy_arn(resource=policy_name)
        mock_get_standard_policy_name_and_arn.return_value = (
            policy_name,
            policy_arn,
        )
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        # If the client raises NoSuchEntityException, no policy exists yet.
        mock_iam_client.exceptions.NoSuchEntityException = Exception
        mock_iam_client.get_policy.side_effect = (
            mock_iam_client.exceptions.NoSuchEntityException
        )

        mock_iam_client.create_policy.return_value = {
            'Policy': {'Arn': policy_arn}
        }
        result = iam.ensure_cloudigrade_policy(mock_session)
        self.assertEqual(result[0], policy_name)
        self.assertEqual(result[1], policy_arn)

        mock_iam_client.list_policy_versions.assert_not_called()
        mock_iam_client.delete_policy_version.assert_not_called()
        mock_iam_client.create_policy_version.assert_not_called()

    @patch('util.aws.iam.get_standard_policy_name_and_arn')
    def test_ensure_cloudigrade_policy_new_version(
        self, mock_get_standard_policy_name_and_arn
    ):
        """Assert ensure_cloudigrade_policy creates a new policy version."""
        policy_name = _faker.slug()
        policy_arn = helper.generate_dummy_arn(resource=policy_name)
        mock_get_standard_policy_name_and_arn.return_value = (
            policy_name,
            policy_arn,
        )
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        mock_iam_client.list_policy_versions.return_value = {
            'Versions': [
                {
                    'CreateDate': '2019-01-02T03:04:05',
                    'IsDefaultVersion': True,
                    'VersionId': 'v1',
                }
            ]
        }

        mock_iam_client.create_policy.return_value = {
            'Policy': {'Arn': policy_arn}
        }
        result = iam.ensure_cloudigrade_policy(mock_session)
        self.assertEqual(result[0], policy_name)
        self.assertEqual(result[1], policy_arn)

        mock_iam_client.create_policy_version.assert_called()
        mock_iam_client.delete_policy_version.assert_not_called()

    @patch('util.aws.iam.get_standard_policy_name_and_arn')
    def test_ensure_cloudigrade_policy_new_version_delete_old(
        self, mock_get_standard_policy_name_and_arn
    ):
        """
        Assert ensure_cloudigrade_policy creates new, deletes old version.

        This use case differs from test_ensure_cloudigrade_policy_new_version
        because AWS has a cap on the number of policy versions and does not
        automatically delete the oldest versions. Sometimes we have to choose
        and explicitly delete a version before we can create a new one.
        """
        policy_name = _faker.slug()
        policy_arn = helper.generate_dummy_arn(resource=policy_name)
        mock_get_standard_policy_name_and_arn.return_value = (
            policy_name,
            policy_arn,
        )
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        mock_iam_client.list_policy_versions.return_value = {
            'Versions': [
                {
                    'CreateDate': '2019-05-02T03:04:05',
                    'IsDefaultVersion': True,
                    'VersionId': 'v5',
                },
                {
                    'CreateDate': '2019-04-02T03:04:05',
                    'IsDefaultVersion': False,
                    'VersionId': 'v4',
                },
                {
                    'CreateDate': '2019-03-02T03:04:05',
                    'IsDefaultVersion': False,
                    'VersionId': 'v3',
                },
                {
                    'CreateDate': '2019-02-02T03:04:05',
                    'IsDefaultVersion': False,
                    'VersionId': 'v2',
                },
                {
                    'CreateDate': '2019-01-02T03:04:05',
                    'IsDefaultVersion': False,
                    'VersionId': 'v1',
                },
            ]
        }

        mock_iam_client.create_policy.return_value = {
            'Policy': {'Arn': policy_arn}
        }
        result = iam.ensure_cloudigrade_policy(mock_session)
        self.assertEqual(result[0], policy_name)
        self.assertEqual(result[1], policy_arn)

        mock_iam_client.delete_policy_version.assert_called_with(
            PolicyArn=policy_arn, VersionId='v1'
        )
        mock_iam_client.create_policy_version.assert_called()

    @patch('util.aws.iam.get_standard_policy_name_and_arn')
    def test_ensure_cloudigrade_policy_arn_mismatch_raises_exception(
        self, mock_get_standard_policy_name_and_arn
    ):
        """
        Assert ensure_cloudigrade_policy raises exception upon unexpected ARN.

        This generally should not be necessary, but if AWS's created Policy ARN
        doesn't match our expected pattern exactly, we need to raise this as an
        error because subsequent operations will fail.
        """
        policy_name = _faker.slug()
        expected_policy_arn = helper.generate_dummy_arn(resource=policy_name)
        created_policy_arn = helper.generate_dummy_arn(resource=policy_name)
        self.assertNotEqual(expected_policy_arn, created_policy_arn)

        mock_get_standard_policy_name_and_arn.return_value = (
            policy_name,
            expected_policy_arn,
        )
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        # If the client raises NoSuchEntityException, no policy exists yet.
        mock_iam_client.exceptions.NoSuchEntityException = Exception
        mock_iam_client.get_policy.side_effect = (
            mock_iam_client.exceptions.NoSuchEntityException
        )

        mock_iam_client.create_policy.return_value = {
            'Policy': {'Arn': created_policy_arn}
        }
        with self.assertRaises(exceptions.AwsPolicyCreationException):
            iam.ensure_cloudigrade_policy(mock_session)

        mock_iam_client.list_policy_versions.assert_not_called()
        mock_iam_client.delete_policy_version.assert_not_called()
        mock_iam_client.create_policy_version.assert_not_called()
