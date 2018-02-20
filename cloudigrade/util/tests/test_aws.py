"""Collection of tests for ``util.aws`` module."""
import json
import uuid
from unittest.mock import patch

from botocore.exceptions import ClientError
import faker
from django.test import TestCase

from util import aws
from util.aws import extract_account_id_from_arn
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
            actual_regions = aws.get_regions(mock_session)
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
            actual_regions = aws.get_regions(mock_session, 'tng')
            self.assertTrue(mock_session.get_available_regions.called)
            mock_session.get_available_regions.assert_called_with('tng')
        self.assertListEqual(mock_regions, actual_regions)

    def test_get_session(self):
        """Assert get_session returns session object."""
        mock_arn = helper.generate_dummy_arn()
        mock_account_id = extract_account_id_from_arn(mock_arn)
        mock_role = {
            'Credentials': {
                'AccessKeyId': str(uuid.uuid4()),
                'SecretAccessKey': str(uuid.uuid4()),
                'SessionToken': str(uuid.uuid4()),
            },
            'foo': 'bar',
        }

        with patch.object(aws.boto3, 'client') as mock_client:
            mock_assume_role = mock_client.return_value.assume_role
            mock_assume_role.return_value = mock_role

            session = aws.get_session(mock_arn)
            creds = session.get_credentials().get_frozen_credentials()

            mock_client.assert_called_with('sts')
            mock_assume_role.assert_called_with(
                Policy=json.dumps(aws.cloudigrade_policy),
                RoleArn=mock_arn,
                RoleSessionName=f'cloudigrade-{mock_account_id}'
            )

        self.assertEquals(creds[0], mock_role['Credentials']['AccessKeyId'])
        self.assertEquals(
            creds[1],
            mock_role['Credentials']['SecretAccessKey']
        )
        self.assertEquals(creds[2], mock_role['Credentials']['SessionToken'])

    def test_get_running_instances(self):
        """Assert we get expected instances in a dict keyed by regions."""
        mock_arn = helper.generate_dummy_arn()
        mock_regions = [f'region-{uuid.uuid4()}']
        mock_role = {
            'Credentials': {
                'AccessKeyId': str(uuid.uuid4()),
                'SecretAccessKey': str(uuid.uuid4()),
                'SessionToken': str(uuid.uuid4()),
            },
            'foo': 'bar',
        }
        mock_running_instance = helper.generate_dummy_describe_instance(
            state=aws.InstanceState.running
        )
        mock_stopped_instance = helper.generate_dummy_describe_instance(
            state=aws.InstanceState.stopped
        )
        mock_described = {
            'Reservations': [
                {
                    'Instances': [
                        mock_running_instance,
                        mock_stopped_instance,
                    ],
                },
            ],
        }
        expected_found = {
            mock_regions[0]: [mock_running_instance]
        }

        with patch.object(aws, 'get_regions') as mock_get_regions, \
                patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role
            mock_get_regions.return_value = mock_regions
            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_client.describe_instances.return_value = mock_described

            actual_found = aws.get_running_instances(aws.get_session(mock_arn))

        self.assertDictEqual(expected_found, actual_found)

    def test_verify_account_access_success(self):
        """Assert that account access via a IAM role is verified."""
        mock_arn = helper.generate_dummy_arn()
        mock_role = {
            'Credentials': {
                'AccessKeyId': str(uuid.uuid4()),
                'SecretAccessKey': str(uuid.uuid4()),
                'SessionToken': str(uuid.uuid4()),
            },
            'foo': 'bar',
        }
        mock_dry_run_exception = {
            'Error': {
                'Code': 'DryRunOperation',
                'Message': 'Request would have succeeded, '
                           'but DryRun flag is set.'
            }
        }
        with patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role

            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_describe_images = mock_client.describe_images
            mock_describe_instances = mock_client.describe_instances
            mock_describe_snapshot_attribute = \
                mock_client.describe_snapshot_attribute
            mock_describe_snapshots = mock_client.describe_snapshots
            mock_modify_snapshot_attribute = \
                mock_client.modify_snapshot_attribute
            mock_modify_image_attribute = mock_client.modify_image_attribute

            mock_describe_images.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeImages')
            mock_describe_instances.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeInstances')
            mock_describe_snapshot_attribute.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeSnapshotAttribute')
            mock_describe_snapshots.side_effect = ClientError(
                mock_dry_run_exception, 'DescribeSnapshots')
            mock_modify_snapshot_attribute.side_effect = ClientError(
                mock_dry_run_exception, 'ModifySnapshotAttribute')
            mock_modify_image_attribute.side_effect = ClientError(
                mock_dry_run_exception, 'ModifyImageAttribute')

            actual_verified = aws.verify_account_access(
                aws.get_session(mock_arn))

            mock_describe_images.assert_called_with(DryRun=True)
            mock_describe_instances.assert_called_with(DryRun=True)
            mock_describe_snapshot_attribute.assert_called_with(
                DryRun=True,
                SnapshotId='string',
                Attribute='productCodes'
            )
            mock_describe_snapshots.assert_called_with(DryRun=True)
            mock_modify_snapshot_attribute.assert_called_with(
                SnapshotId='string',
                DryRun=True,
                Attribute='productCodes',
                GroupNames=['string', ]
            )
            mock_modify_image_attribute.assert_called_with(
                Attribute='description',
                ImageId='string',
                DryRun=True
            )

        self.assertTrue(actual_verified)

    def test_verify_account_access_failure(self):
        """Assert that account access via a IAM role is not verified."""
        mock_arn = helper.generate_dummy_arn()
        mock_role = {
            'Credentials': {
                'AccessKeyId': str(uuid.uuid4()),
                'SecretAccessKey': str(uuid.uuid4()),
                'SessionToken': str(uuid.uuid4()),
            },
            'foo': 'bar',
        }
        mock_unauthorized_exception = {
            'Error': {
                'Code': 'UnauthorizedOperation',
                'Message': 'You are not authorized '
                           'to perform this operation.'
            }
        }
        mock_garbage_exception = {
            'Error': {
                'Code': 'GarbageOperation',
                'Message': 'You are not authorized '
                           'to perform this garbage operation.'
            }
        }
        bad_policy = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Sid': 'CloudigradeGarbagePolicy',
                    'Effect': 'Allow',
                    'Action': [
                        'ec2:DescribeGarbage'
                    ],
                    'Resource': '*'
                }
            ]
        }

        with patch.object(aws, 'boto3') as mock_boto3:
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = mock_role

            mock_client = mock_boto3.Session.return_value.client.return_value
            mock_describe_images = mock_client.describe_images
            mock_describe_instances = mock_client.describe_instances
            mock_describe_snapshot_attribute = \
                mock_client.describe_snapshot_attribute
            mock_describe_snapshots = mock_client.describe_snapshots
            mock_modify_snapshot_attribute = \
                mock_client.modify_snapshot_attribute
            mock_modify_image_attribute = mock_client.modify_image_attribute

            mock_describe_images.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeImages')
            mock_describe_instances.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeInstances')
            mock_describe_snapshot_attribute.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeSnapshotAttribute')
            mock_describe_snapshots.side_effect = ClientError(
                mock_unauthorized_exception, 'DescribeSnapshots')
            mock_modify_snapshot_attribute.side_effect = ClientError(
                mock_unauthorized_exception, 'ModifySnapshotAttribute')
            mock_modify_image_attribute.side_effect = ClientError(
                mock_unauthorized_exception, 'ModifyImageAttribute')

            session = aws.get_session(mock_arn)
            actual_verified = aws.verify_account_access(session)

            mock_describe_images.side_effect = ClientError(
                mock_garbage_exception, 'DescribeImages')
            with self.assertRaises(ClientError) as e:
                    aws.verify_account_access(session)
                    self.assertContains(e, 'GarbageOperation')

            with patch.dict(aws.cloudigrade_policy, bad_policy):
                aws.verify_account_access(session)

            mock_describe_images.assert_called_with(DryRun=True)
            mock_describe_instances.assert_called_with(DryRun=True)
            mock_describe_snapshot_attribute.assert_called_with(
                DryRun=True,
                SnapshotId='string',
                Attribute='productCodes'
            )
            mock_describe_snapshots.assert_called_with(DryRun=True)
            mock_modify_snapshot_attribute.assert_called_with(
                SnapshotId='string',
                DryRun=True,
                Attribute='productCodes',
                GroupNames=['string', ]
            )
            mock_modify_image_attribute.assert_called_with(
                Attribute='description',
                ImageId='string',
                DryRun=True
            )

        self.assertFalse(actual_verified)
