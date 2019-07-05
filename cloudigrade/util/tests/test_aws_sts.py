"""Collection of tests for ``util.aws.sts`` module."""
import json
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TestCase

from util.aws import AwsArn
from util.aws import sts
from util.tests import helper


class UtilAwsStsTest(TestCase):
    """AWS STS utility functions test case."""

    @patch('util.aws.sts.boto3.client')
    def test_get_session(self, mock_client):
        """Assert get_session returns session object."""
        mock_arn = AwsArn(helper.generate_dummy_arn())
        mock_account_id = mock_arn.account_id
        mock_role = helper.generate_dummy_role()

        mock_assume_role = mock_client.return_value.assume_role
        mock_assume_role.return_value = mock_role

        session = sts.get_session(str(mock_arn))
        creds = session.get_credentials().get_frozen_credentials()

        mock_client.assert_called_with('sts')
        mock_assume_role.assert_called_with(
            Policy=json.dumps(sts.cloudigrade_policy),
            RoleArn='{0}'.format(mock_arn),
            RoleSessionName='cloudigrade-{0}'.format(mock_account_id)
        )

        self.assertEqual(creds[0], mock_role['Credentials']['AccessKeyId'])
        self.assertEqual(
            creds[1],
            mock_role['Credentials']['SecretAccessKey']
        )
        self.assertEqual(creds[2], mock_role['Credentials']['SessionToken'])

    def test_get_session_account_id(self):
        """Assert successful return of the account ID through the session."""
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_identity = mock_client.get_caller_identity.return_value
        mock_account_id = mock_identity.get.return_value
        returned_account_id = sts.get_session_account_id(mock_session)
        self.assertEqual(mock_account_id, returned_account_id)
        mock_identity.get.assert_called_with('Account')

    def test_get_session_account_id_bad_session(self):
        """Test failure handling when the session is invalid."""
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_identity = mock_client.get_caller_identity.return_value
        mock_identity.get.side_effect = ClientError(
            error_response={'Error': {'Code': 'InvalidClientTokenId'}},
            operation_name=None,
        )
        returned_account_id = sts.get_session_account_id(mock_session)
        self.assertIsNone(returned_account_id)
        mock_identity.get.assert_called_with('Account')

    def test_get_session_account_id_mystery_error(self):
        """Test failure handling when AWS raises error unexpectedly."""
        mock_session = Mock()
        mock_client = mock_session.client.return_value
        mock_identity = mock_client.get_caller_identity.return_value
        mock_identity.get.side_effect = ClientError(
            error_response={'Error': {'Code': 'TooBadSoSad'}},
            operation_name=None,
        )
        with self.assertRaises(ClientError):
            sts.get_session_account_id(mock_session)
        mock_identity.get.assert_called_with('Account')
