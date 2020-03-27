"""Collection of tests for api.cloud.aws.util.create_aws_cloud_account."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.aws import util
from api.models import CloudAccount
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateAWSClountTest(TestCase):
    """Test cases for api.cloud.aws.util.create_aws_cloud_account."""

    def setUp(self):
        """Set up shared variables."""
        self.user = util_helper.generate_test_user()
        self.arn = util_helper.generate_dummy_arn()
        self.name = _faker.word()
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.endpoint_id = _faker.pyint()
        self.source_id = _faker.pyint()

    @patch.object(CloudAccount, "enable")
    def test_create_aws_clount_success(self, mock_enable):
        """Test create_aws_cloud_account success."""
        util.create_aws_cloud_account(
            self.user,
            self.arn,
            self.name,
            self.auth_id,
            self.app_id,
            self.endpoint_id,
            self.source_id,
        )

        mock_enable.assert_called()
