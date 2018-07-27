"""Collection of tests for ``util.aws.cloudtrail`` module."""

from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from util.aws import cloudtrail
from util.tests import helper


class UtilAwsCloudTrailTest(TestCase):
    """AWS CloudTrail utility functions test case."""

    @patch('util.aws.cloudtrail.trail_exists', return_value=True)
    def test_configure_cloudtrail_update(self, mock_trail_exists):
        """
        Test the configure_cloudtrail function.

        Assert that update_trail is called if the CloudTrail previously
        exists and that the response is the output of update_trail.
        """
        mock_session = Mock()
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        expected_response = {
            'Name': name,
            'S3BucketName': 'foo-s3',
            'IncludeGlobalServiceEvents': True,
            'IsMultiRegionTrail': True,
            'TrailARN': 'arn:aws:cloudtrail:us-east-1:'
            '{0}:trail/{1}'.format(aws_account_id, name),
            'LogFileValidationEnabled': False,
            'ResponseMetadata': {
                'RequestId': '398432984738',
                'HTTPStatusCode': 200,
                'HTTPHeaders': {
                    'x-amzn-requestid': '56564546',
                    'content-type': 'application/x-amz-json-1.1',
                    'content-length': '253'
                },
                'RetryAttempts': 0
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.update_trail.return_value = expected_response
        mock_client.put_event_selectors.return_value = None

        actual_response = cloudtrail.configure_cloudtrail(mock_session,
                                                          aws_account_id)

        self.assertEqual(expected_response, actual_response)

    @patch('util.aws.cloudtrail.trail_exists', return_value=False)
    def test_configure_cloudtrail_create(self, mock_trail_exists):
        """
        Test the configure_cloudtrail function.

        Assert that create_cloudtrail function is called if the CloudTrail
        does not exist and the response is the output of create_trail.
        """
        mock_session = Mock()
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        expected_response = {
            'Name': name,
            'S3BucketName': 'foo-s3',
            'IncludeGlobalServiceEvents': True,
            'IsMultiRegionTrail': True,
            'TrailARN': 'arn:aws:cloudtrail:us-east-1:'
            '{0}:trail/{1}'.format(aws_account_id, name),
            'LogFileValidationEnabled': False,
            'ResponseMetadata': {
                'RequestId': '398432984738',
                'HTTPStatusCode': 200,
                'HTTPHeaders': {
                    'x-amzn-requestid': '56564546',
                    'content-type': 'application/x-amz-json-1.1',
                    'content-length': '253',
                },
                'RetryAttempts': 0
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.create_trail.return_value = expected_response
        mock_client.put_event_selectors.return_value = None

        actual_response = cloudtrail.configure_cloudtrail(mock_session,
                                                          aws_account_id)

        self.assertEqual(expected_response, actual_response)

    def test_trail_exists_found(self):
        """Test the trail_exists function.

        Assert that the trail_exists function returns True when the CloudTrail
        name is found within the trail list returned from the describe_trails
        function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_traillist = {
            'trailList': [{
                'Name': name,
                'S3BucketName': 'foo-s3',
                'IncludeGlobalServiceEvents': True,
                'IsMultiRegionTrail': True,
                'HomeRegion': 'us-east-1',
                'TrailARN': 'arn:aws:cloudtrail:us-east-1:'
                '{0}:trail/{1}'.format(aws_account_id, name),
                'LogFileValidationEnabled': False,
                'HasCustomEventSelectors': True
            }]
        }

        mock_client = mock_session.client.return_value
        mock_client.describe_trails.return_value = mock_traillist

        expected_trail_exists_value = True
        actual_trail_exists_value = cloudtrail.trail_exists(mock_client, name)
        self.assertEqual(expected_trail_exists_value,
                         actual_trail_exists_value)

    def test_trail_exists_not_found(self):
        """Test the trail_exists function.

        Assert that the trail_exists function returns False when the CloudTrail
        name is found within the trail list returned from the describe_trails
        function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_trailList = {
            'trailList': []
        }

        mock_client = mock_session.client.return_value
        mock_client.describe_trails.return_value = mock_trailList

        expected_trail_exists_value = False
        actual_trail_exists_value = cloudtrail.trail_exists(mock_client, name)
        self.assertEqual(expected_trail_exists_value,
                         actual_trail_exists_value)

    def test_put_event_selectors(self):
        """Test the put_event_selectors function.

        Assert that put_event_selectors returns the response returned from
        calling the cloudtrail put_event_selectors function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_response = {
            'TrailARN': 'arn:aws:cloudtrail:us-east-1:'
            '{0}:trail/{1}'.format(aws_account_id, name),
            'EventSelectors': [{
                'ReadWriteType': 'WriteOnly',
                'IncludeManagementEvents': True,
                'DataResources': []
            }],
        }

        mock_client = mock_session.client.return_value
        # set the aws put_event_selectors function response as mock_response
        mock_client.put_event_selectors.return_value = mock_response

        # set the expected response as the mock_response as well
        expected_return_value = mock_response

        actual_return_value = cloudtrail.put_event_selectors(mock_client, name)
        self.assertEqual(expected_return_value, actual_return_value)

    def test_put_event_selectors_exception(self):
        """Test the put_event_selectors function.

        Assert that an error is returned when the CloudTrail does not exist.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_error = {
            'Error': {
                'Code': 'TrailNotFoundException',
                'Message':
                    'Unknown trail: {0} for the user '
                    '{1}'.format(name, aws_account_id)
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.put_event_selectors.side_effect = ClientError(
            mock_error, 'PutEventSelectors')

        with self.assertRaises(ClientError):
            cloudtrail.put_event_selectors(mock_client, name)

    def test_create_cloudtrail(self):
        """Test the create_cloudtrail function.

        Assert that create_cloudtrail function returns the response returned
        from calling the cloudtrail create_cloudtrail function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_response = {
            'TrailARN': 'arn:aws:cloudtrail:us-east-1:'
            '{0}:trail/{1}'.format(aws_account_id, name),
            'EventSelectors': [{
                'ReadWriteType': 'WriteOnly',
                'IncludeManagementEvents': True,
                'DataResources': []
            }],
            'ResponseMetadata': {
                'RequestId': '02280e28-06ba-4384-af0e-b8f72b9a8a53',
                'HTTPStatusCode': 200,
                'HTTPHeaders': {
                    'x-amzn-requestid': '02280e28-06ba-4384-af0e-b8f72b9a8a53',
                    'content-type': 'application/x-amz-json-1.1',
                    'content-length': '186',
                    'date': 'Fri, 22 Jun 2018 14:29:56 GMT'
                },
                'RetryAttempts': 0
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.create_trail.return_value = mock_response

        expected_value = mock_response
        actual_value = cloudtrail.create_cloudtrail(mock_client, name)
        self.assertEqual(expected_value, actual_value)

    def test_create_cloudtrail_exception(self):
        """Test the create_cloudtrail function.

        Assert that an error is returned when the trail already exists
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_error = {
            'Error': {
                'Code': 'TrailAlreadyExistsException',
                'Message':
                    'Trail {0} already exists'
                    'for customer: {1}'.format(name,
                                               aws_account_id)
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.create_trail.side_effect = ClientError(
            mock_error, 'CreateTrail')

        with self.assertRaises(ClientError):
            cloudtrail.create_cloudtrail(mock_client, name)

    def test_update_cloudtrail(self):
        """Test the update_cloudtrail function.

        Assert that update_cloudtrail function returns the response returned
        from calling the cloudtrail update_trail function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_response = {
            'Name': name,
            'S3BucketName': 'foo-s3',
            'IncludeGlobalServiceEvents': True,
            'IsMultiRegionTrail': True,
            'TrailARN': 'arn:aws:cloudtrail:us-east-1:'
            '{0}:trail/{1}'.format(aws_account_id, name),
            'LogFileValidationEnabled': False,
            'ResponseMetadata': {
                'RequestId': '398432984738',
                'HTTPStatusCode': 200,
                'HTTPHeaders': {
                    'x-amzn-requestid': '56564546',
                    'content-type': 'application/x-amz-json-1.1',
                    'content-length': '253',
                },
                'RetryAttempts': 0
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.update_trail.return_value = mock_response

        expected_value = mock_response
        actual_value = cloudtrail.update_cloudtrail(mock_client, name)
        self.assertEqual(expected_value, actual_value)

    def test_update_cloudtrail_exception(self):
        """
        Test the update_cloudtrail function.

        Assert that an error is returned when the CloudTrail does not exist.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = '{0}{1}'.format(settings.CLOUDTRAIL_NAME_PREFIX,
                               aws_account_id)

        mock_session = Mock()

        mock_copy_error = {
            'Error': {
                'Code': 'TrailNotFoundException',
                'Message':
                    'Unknown trail: {0} for the user '
                    '{1}'.format(name, aws_account_id)
            }
        }

        mock_client = mock_session.client.return_value

        mock_client.update_trail.side_effect = ClientError(mock_copy_error,
                                                           'UpdateTrail')

        with self.assertRaises(ClientError):
            cloudtrail.update_cloudtrail(mock_client, name)
