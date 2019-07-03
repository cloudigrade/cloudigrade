"""Collection of tests for ``util.aws.sts`` module."""
import json
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

    @patch('util.aws.iam.get_session_account_id')
    @patch('util.aws.iam._get_primary_account_id')
    def test_get_standard_role_name_and_arn(
        self, mock_get_primary_account_id, mock_get_session_account_id
    ):
        """Assert get_standard_role_name_and_arn returns expected values."""
        system_account_id = helper.generate_dummy_aws_account_id()
        customer_account_id = helper.generate_dummy_aws_account_id()

        mock_get_primary_account_id.return_value = system_account_id
        mock_get_session_account_id.return_value = customer_account_id

        mock_session = Mock()
        policy_name, policy_arn = iam.get_standard_role_name_and_arn(
            mock_session
        )
        mock_get_session_account_id.assert_called_with(mock_session)
        mock_get_primary_account_id.assert_called()

        arn = AwsArn(policy_arn)
        self.assertEqual(arn.account_id, customer_account_id)
        self.assertEqual(arn.service, 'iam')
        self.assertEqual(arn.resource_type, 'role')
        self.assertIn(str(system_account_id), arn.resource)

    @patch('util.aws.iam._get_primary_account_id')
    def test_get_standard_assume_role_policy_document(
        self, mock_get_primary_account_id
    ):
        """Assert _get_primary_account_id returns expected document str."""
        primary_account_id = helper.generate_dummy_aws_account_id()
        mock_get_primary_account_id.return_value = primary_account_id
        document = iam.get_standard_assume_role_policy_document()
        document_dict = json.loads(document)
        self.assertIn(
            str(primary_account_id),
            document_dict['Statement'][0]['Principal']['AWS'],
        )
        self.assertEqual(
            document_dict['Statement'][0]['Action'], 'sts:AssumeRole'
        )

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

    @patch('util.aws.iam.get_standard_role_name_and_arn')
    @patch('util.aws.iam.get_standard_assume_role_policy_document')
    def test_ensure_cloudigrade_role_new(
        self,
        mock_get_standard_assume_role_policy_document,
        mock_get_standard_role_name_and_arn,
    ):
        """
        Test ensure_cloudigrade_role happy path for new role.

        When we create an IAM Role, we attach the AssumeRolePolicyDocument. So,
        the general interaction with AWS API looks like:

        - get_role returns None
        - create_role returns our new Role
        - do not call update_assume_role_policy because the Role created should
          already be correct
        - list_attached_role_policies returns empty list
        - attach_role_policy attaches our Policy to the Role
        """
        role_name = _faker.slug()
        role_arn = helper.generate_dummy_arn(resource=role_name)
        mock_get_standard_role_name_and_arn.return_value = (
            role_name,
            role_arn,
        )

        policy_document = {'my_great_policy': 'goes here'}
        policy_document_str = json.dumps(policy_document)
        mock_get_standard_assume_role_policy_document.return_value = (
            policy_document_str
        )

        policy_arn = helper.generate_dummy_arn()
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        # If the client raises NoSuchEntityException, no role exists yet.
        mock_iam_client.exceptions.NoSuchEntityException = Exception
        mock_iam_client.get_role.side_effect = (
            mock_iam_client.exceptions.NoSuchEntityException
        )

        # Fake role response from the mock client.
        # Note that the AssumeRolePolicyDocument has the dict, not str.
        created_role = {
            'Role': {
                'Arn': role_arn,
                'RoleName': role_name,
                'AssumeRolePolicyDocument': policy_document,
            }
        }
        mock_iam_client.create_role.return_value = created_role

        # Fake attached role policies list from the mock client.
        mock_iam_client.list_attached_role_policies.return_value = {
            'AttachedPolicies': []
        }

        result = iam.ensure_cloudigrade_role(mock_session, policy_arn)

        # See the test docstring for rationale of each of these AWS calls:
        mock_iam_client.get_role.assert_called_with(RoleName=role_name)
        mock_iam_client.create_role.assert_called_with(
            RoleName=role_name, AssumeRolePolicyDocument=policy_document_str
        )
        mock_iam_client.update_assume_role_policy.assert_not_called()
        mock_iam_client.list_attached_role_policies.assert_called_with(
            RoleName=role_name
        )
        mock_iam_client.attach_role_policy.assert_called_with(
            RoleName=role_name, PolicyArn=policy_arn
        )

        self.assertEqual(result, (role_name, role_arn))

    @patch('util.aws.iam.get_standard_role_name_and_arn')
    @patch('util.aws.iam.get_standard_assume_role_policy_document')
    def test_ensure_cloudigrade_role_update_no_changes(
        self,
        mock_get_standard_assume_role_policy_document,
        mock_get_standard_role_name_and_arn,
    ):
        """
        Test ensure_cloudigrade_role happy path to update role with no changes.

        In this case, the Role is already correctly configured. So, the general
        interaction with AWS API looks like:

        - get_role returns our Role
        - do not call update_assume_role_policy because the Role created should
          already be correct
        - list_attached_role_policies returns list with our attachment
        - do not call attach_role_policy because it already exists
        """
        role_name = _faker.slug()
        role_arn = helper.generate_dummy_arn(resource=role_name)
        mock_get_standard_role_name_and_arn.return_value = (
            role_name,
            role_arn,
        )

        policy_document = {'my_great_policy': 'goes here'}
        policy_document_str = json.dumps(policy_document)
        mock_get_standard_assume_role_policy_document.return_value = (
            policy_document_str
        )

        policy_arn = helper.generate_dummy_arn()
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        # Fake role response from the mock client.
        # Note that the AssumeRolePolicyDocument has the dict, not str.
        existing_role = {
            'Role': {
                'Arn': role_arn,
                'RoleName': role_name,
                'AssumeRolePolicyDocument': policy_document,
            }
        }
        mock_iam_client.get_role.return_value = existing_role

        # Fake attached role policies list from the mock client.
        mock_iam_client.list_attached_role_policies.return_value = {
            'AttachedPolicies': [{'PolicyArn': policy_arn}]
        }

        result = iam.ensure_cloudigrade_role(mock_session, policy_arn)

        # See the test docstring for rationale of each of these AWS calls:
        mock_iam_client.get_role.assert_called_with(RoleName=role_name)
        mock_iam_client.create_role.assert_not_called()
        mock_iam_client.update_assume_role_policy.assert_not_called()
        mock_iam_client.list_attached_role_policies.assert_called_with(
            RoleName=role_name
        )
        mock_iam_client.attach_role_policy.assert_not_called()

        self.assertEqual(result, (role_name, role_arn))

    @patch('util.aws.iam.get_standard_role_name_and_arn')
    @patch('util.aws.iam.get_standard_assume_role_policy_document')
    def test_ensure_cloudigrade_role_update_policy_document(
        self,
        mock_get_standard_assume_role_policy_document,
        mock_get_standard_role_name_and_arn,
    ):
        """
        Test ensure_cloudigrade_role updates role with wrong policy document.

        In this case, the Role is already partially configured. So, the general
        interaction with AWS API looks like:

        - get_role returns our Role with incorrect policy document
        - call update_assume_role_policy with the correct policy document
        - list_attached_role_policies returns list with our attachment
        - do not call attach_role_policy because it already exists
        """
        role_name = _faker.slug()
        role_arn = helper.generate_dummy_arn(resource=role_name)
        mock_get_standard_role_name_and_arn.return_value = (
            role_name,
            role_arn,
        )

        policy_document = {'my_great_policy': 'goes here'}
        policy_document_str = json.dumps(policy_document)
        mock_get_standard_assume_role_policy_document.return_value = (
            policy_document_str
        )

        policy_arn = helper.generate_dummy_arn()
        mock_session = Mock()
        mock_iam_client = mock_session.client.return_value

        # Fake role response from the mock client with *bad* policy document.
        existing_role = {
            'Role': {
                'Arn': role_arn,
                'RoleName': role_name,
                'AssumeRolePolicyDocument': '{}',
            }
        }
        mock_iam_client.get_role.return_value = existing_role

        # Fake attached role policies list from the mock client.
        mock_iam_client.list_attached_role_policies.return_value = {
            'AttachedPolicies': [{'PolicyArn': policy_arn}]
        }

        result = iam.ensure_cloudigrade_role(mock_session, policy_arn)

        # See the test docstring for rationale of each of these AWS calls:
        mock_iam_client.get_role.assert_called_with(RoleName=role_name)
        mock_iam_client.create_role.assert_not_called()
        mock_iam_client.update_assume_role_policy.assert_called_with(
            RoleName=role_name, PolicyDocument=policy_document_str
        )
        mock_iam_client.list_attached_role_policies.assert_called_with(
            RoleName=role_name
        )
        mock_iam_client.attach_role_policy.assert_not_called()

        self.assertEqual(result, (role_name, role_arn))
