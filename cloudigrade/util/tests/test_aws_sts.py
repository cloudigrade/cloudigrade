"""Collection of tests for ``util.aws.sts`` module."""
import json
from unittest.mock import patch

from django.test import TestCase

from util.aws import AwsArn
from util.aws import sts
from util.tests import helper


class UtilAwsStsTest(TestCase):
    """AWS STS utility functions test case."""

    @patch('util.aws.sts.boto3.client')
    def test_get_session(self, mock_client):
        """Assert get_session returns session object."""
        mock_arn = AwsArn(helper.generate_dummy_arn(generate_account_id=True))
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
