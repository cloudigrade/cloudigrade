"""Collection of tests for ``util.aws.cloudtrail`` module."""

from unittest.mock import Mock, patch

from django.test import TestCase

from util.aws import configure_cloudtrail
from util.tests import helper

class UtilAwsCloudTrailTest(TestCase):
    """AWS CloudTrail utility functions test case."""

    def test_configure_cloudtrail(self):
        """
        Assert we get expected instances in a dict keyed by regions.

        The setup here is a little complicated, and it's important to
        understand what's going into it. The mock response from the client's
        `describe_instances` includes a Reservations list of **three** elements
        with different Instances in each. It is unclear to us how AWS divides
        Instances into Reservations; so, we must ensure in our tests that we
        are checking for Instances in potentially multiple Reservations.
        """
        mock_role = helper.generate_dummy_role()

        mock_session = Mock()
        mock_assume_role = mock_session.client.return_value.assume_role
        mock_assume_role.return_value = mock_role
        aws_account_id = helper.generate_dummy_aws_account_id()

        mock_described = {
            'Reservations': [
                {
                    'Instances': [
                        mock_running_instance_1,
                        mock_stopped_instance_1,
                    ],
                },
                {
                    'Instances': [
                        mock_running_instance_2,
                    ],
                },
                {
                    'Instances': [
                        mock_stopped_instance_2,
                    ],
                },
            ],
        }

        mock_client = mock_session.client.return_value
        mock_client.configure_cloudtrail.return_value = mock_described

        expected_found = {
            mock_regions[0]: [
                mock_running_instance_1,
                mock_running_instance_2,
            ]
        }

        with patch.object(ec2, 'get_regions') as mock_get_regions:
            mock_get_regions.return_value = mock_regions
            actual_found = ec2.get_running_instances(mock_session)

        cloudtrail = configure_cloudtrail(mock_session,
                                          aws_account_id)

        self.assertDictEqual(expected_found, actual_found)
