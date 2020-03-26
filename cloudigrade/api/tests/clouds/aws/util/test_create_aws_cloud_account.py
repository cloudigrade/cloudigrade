"""Collection of tests for api.cloud.aws.util.create_aws_cloud_account."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.aws import tasks, util
from api.models import CloudAccount
from api.tests import helper as api_helper
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

    @patch.object(tasks, "initial_aws_describe_instances")
    def test_create_aws_clount_success(self, mock_initial_describe):
        """Test create_aws_cloud_account success."""
        cloud_account = util.create_aws_cloud_account(
            self.user,
            self.arn,
            self.name,
            self.auth_id,
            self.app_id,
            self.endpoint_id,
            self.source_id,
        )

        self.assertTrue(cloud_account.is_enabled)

    @patch.object(tasks, "initial_aws_describe_instances")
    @patch.object(CloudAccount, "enable")
    def test_create_duplicate_aws_clount_reenables_account(
        self, mock_enable, mock_initial_describe
    ):
        """Test enable is called if clount already exists."""
        api_helper.generate_aws_account(
            arn=self.arn,
            user=self.user,
            name=self.name,
            authentication_id=self.auth_id,
            application_id=self.app_id,
            endpoint_id=self.endpoint_id,
            source_id=self.source_id,
            is_enabled=False,
        )

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
