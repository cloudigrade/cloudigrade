"""Collection of tests for api.cloud.aws.util.update_aws_cloud_account."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.aws import util
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class UpdateAWSClountTest(TestCase):
    """Test cases for api.cloud.aws.util.update_aws_cloud_account."""

    def setUp(self):
        """Set up shared variables."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.arn = util_helper.generate_dummy_arn(account_id=self.aws_account_id)
        self.name = _faker.word()
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.source_id = _faker.pyint()

        self.clount = api_helper.generate_cloud_account(
            arn=self.arn,
            aws_account_id=self.aws_account_id,
            user=self.user,
            name=self.name,
            platform_authentication_id=self.auth_id,
            platform_application_id=self.app_id,
            platform_source_id=self.source_id,
        )

    @patch("api.error_codes.notify_sources_application_availability")
    def test_update_aws_clount_notifies_sources_invalid_arn(self, mock_notify_sources):
        """Test update_aws_cloud_account notifies sources if ARN is invalid."""
        util.update_aws_cloud_account(
            self.clount, "INVALID", self.name, self.auth_id, self.source_id
        )
        mock_notify_sources.assert_called()
