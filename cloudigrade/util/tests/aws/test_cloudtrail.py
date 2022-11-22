"""Collection of tests for ``util.aws.cloudtrail`` module."""

from unittest.mock import Mock

from botocore.exceptions import ClientError
from django.conf import settings
from django.test import TestCase

from util.aws import cloudtrail
from util.tests import helper


class UtilAwsCloudTrailTest(TestCase):
    """AWS CloudTrail utility functions test case."""

    def test_trail_exists_found(self):
        """Test the trail_exists function.

        Assert that the trail_exists function returns True when the CloudTrail
        name is found within the trail list returned from the describe_trails
        function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = "{0}{1}".format(settings.CLOUDTRAIL_NAME_PREFIX, aws_account_id)

        mock_session = Mock()

        mock_traillist = {
            "trailList": [
                {
                    "Name": name,
                    "S3BucketName": "foo-s3",
                    "IncludeGlobalServiceEvents": True,
                    "IsMultiRegionTrail": True,
                    "HomeRegion": "us-east-1",
                    "TrailARN": "arn:aws:cloudtrail:us-east-1:"
                    "{0}:trail/{1}".format(aws_account_id, name),
                    "LogFileValidationEnabled": False,
                    "HasCustomEventSelectors": True,
                }
            ]
        }

        mock_client = mock_session.client.return_value
        mock_client.describe_trails.return_value = mock_traillist

        expected_trail_exists_value = True
        actual_trail_exists_value = cloudtrail.trail_exists(mock_client, name)
        self.assertEqual(expected_trail_exists_value, actual_trail_exists_value)

    def test_trail_exists_not_found(self):
        """Test the trail_exists function.

        Assert that the trail_exists function returns False when the CloudTrail
        name is not found within the trail list returned from the describe_trails
        function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = "{0}{1}".format(settings.CLOUDTRAIL_NAME_PREFIX, aws_account_id)

        mock_session = Mock()

        mock_trailList = {"trailList": []}

        mock_client = mock_session.client.return_value
        mock_client.describe_trails.return_value = mock_trailList

        expected_trail_exists_value = False
        actual_trail_exists_value = cloudtrail.trail_exists(mock_client, name)
        self.assertEqual(expected_trail_exists_value, actual_trail_exists_value)

    def test_delete_cloudtrail(self):
        """Test the delete_cloudtrail function.

        Assert that delete_cloudtrail function returns the response returned
        from calling the cloudtrail delete_trail function.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = "{0}{1}".format(settings.CLOUDTRAIL_NAME_PREFIX, aws_account_id)

        mock_session = Mock()

        # This was the real response from a delete_trail call made on 2020-07-15.
        mock_response = {
            "ResponseMetadata": {
                "RequestId": "cd3513ab-6c5f-490a-b94f-7dea5faa9e40",
                "HTTPStatusCode": 200,
                "HTTPHeaders": {
                    "x-amzn-requestid": "cd3513ab-6c5f-490a-b94f-7dea5faa9e40",
                    "content-type": "application/x-amz-json-1.1",
                    "content-length": "2",
                    "date": "Wed, 15 Jul 2020 15:31:25 GMT",
                },
                "RetryAttempts": 0,
            }
        }

        mock_client = mock_session.client.return_value
        mock_client.delete_trail.return_value = mock_response
        expected_value = mock_response
        actual_value = cloudtrail.delete_cloudtrail(mock_client, name)

        self.assertEqual(expected_value, actual_value)

    def test_delete_cloudtrail_exception(self):
        """
        Test the delete_cloudtrail function.

        Assert that an error is returned when the CloudTrail does not exist.
        """
        aws_account_id = helper.generate_dummy_aws_account_id()
        name = "{0}{1}".format(settings.CLOUDTRAIL_NAME_PREFIX, aws_account_id)

        mock_session = Mock()

        mock_error = {
            "Error": {
                "Code": "TrailNotFoundException",
                "Message": "Unknown trail: {0} for the user: {1}".format(
                    name, aws_account_id
                ),
            }
        }

        mock_client = mock_session.client.return_value

        mock_client.delete_trail.side_effect = ClientError(mock_error, "DeleteTrail")

        with self.assertRaises(ClientError):
            cloudtrail.delete_cloudtrail(mock_client, name)
