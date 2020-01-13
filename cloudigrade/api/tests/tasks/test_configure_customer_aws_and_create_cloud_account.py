"""Collection of tests for configure_customer_aws_and_create_cloud_account."""
from unittest.mock import patch

import faker
from django.contrib.auth.models import User
from django.test import TestCase

from api import tasks, util as api_util
from util.tests import helper as util_helper

_faker = faker.Faker()


class ConfigureCustomerAwsAndCreateCloudAccountTest(TestCase):
    """Task 'configure_customer_aws_and_create_cloud_account' test cases."""

    @patch.object(tasks, "verify_permissions_and_create_aws_cloud_account")
    @patch.object(tasks, "aws")
    @patch("util.aws.sts._get_primary_account_id")
    def test_success(self, mock_primary_id, mock_tasks_aws, mock_verify):
        """Assert the task happy path upon normal operation."""
        # User that would ultimately own the created objects.
        user = User.objects.create()

        # Dummy values for the various interactions.
        customer_access_key_id = _faker.user_name()
        customer_secret_access_key = _faker.password()
        primary_account_id = util_helper.generate_dummy_aws_account_id()
        mock_primary_id.return_value = primary_account_id
        session_account_id = util_helper.generate_dummy_aws_account_id()
        mock_tasks_aws.get_session_account_id.return_value = session_account_id
        session = mock_tasks_aws.get_session_from_access_key.return_value

        # Fake out the policy verification.
        policy_name = _faker.slug()
        policy_arn = util_helper.generate_dummy_arn()
        mock_ensure_policy = mock_tasks_aws.ensure_cloudigrade_policy
        mock_ensure_policy.return_value = (policy_name, policy_arn)

        # Fake out the role verification.
        role_name = _faker.slug()
        role_arn = util_helper.generate_dummy_arn()
        mock_ensure_role = mock_tasks_aws.ensure_cloudigrade_role
        mock_ensure_role.return_value = (role_name, role_arn)

        tasks.configure_customer_aws_and_create_cloud_account(
            user.id, customer_access_key_id, customer_secret_access_key
        )

        mock_tasks_aws.get_session_account_id.assert_called_with(session)
        mock_ensure_policy.assert_called_with(session)
        mock_ensure_role.assert_called_with(session, policy_arn)
        cloud_account_name = api_util.get_standard_cloud_account_name(
            "aws", session_account_id
        )
        mock_verify.assert_called_with(
            user, role_arn, cloud_account_name, customer_access_key_id
        )

    @patch.object(tasks, "verify_permissions_and_create_aws_cloud_account")
    @patch.object(tasks, "aws")
    def test_fails_if_user_not_found(self, mock_tasks_aws, mock_verify):
        """Assert the task returns early if user is not found."""
        user_id = -1  # This user should never exist.

        customer_access_key_id = _faker.user_name()
        customer_secret_access_key = _faker.password()

        tasks.configure_customer_aws_and_create_cloud_account(
            user_id, customer_access_key_id, customer_secret_access_key
        )

        mock_tasks_aws.get_session_account_id.assert_not_called()
        mock_tasks_aws.ensure_cloudigrade_policy.assert_not_called()
        mock_tasks_aws.ensure_cloudigrade_role.assert_not_called()
        mock_verify.assert_not_called()

    @patch.object(tasks, "verify_permissions_and_create_aws_cloud_account")
    @patch.object(tasks, "aws")
    def test_early_return_if_bad_session(self, mock_tasks_aws, mock_verify):
        """Assert the task returns early if AWS session is invalid."""
        # User that would ultimately own the created objects.
        user = User.objects.create()

        customer_access_key_id = _faker.user_name()
        customer_secret_access_key = _faker.password()

        session = mock_tasks_aws.get_session_from_access_key.return_value
        mock_tasks_aws.get_session_account_id.return_value = None
        mock_ensure_policy = mock_tasks_aws.ensure_cloudigrade_policy
        mock_ensure_role = mock_tasks_aws.ensure_cloudigrade_role

        tasks.configure_customer_aws_and_create_cloud_account(
            user.id, customer_access_key_id, customer_secret_access_key
        )

        mock_tasks_aws.get_session_account_id.assert_called_with(session)
        mock_ensure_policy.assert_not_called()
        mock_ensure_role.assert_not_called()
        mock_verify.assert_not_called()
