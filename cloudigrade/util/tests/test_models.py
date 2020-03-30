"""Collection of tests for Cloudigrade base model logic."""

from unittest.mock import patch

from django.test import TestCase

from api import models
from api.clouds.aws import models as aws_models
from api.tests import helper
from util.aws import sts
from util.tests import helper as util_helper


class BaseGenericModelTest(TestCase):
    """BaseGenericModel Test Cases."""

    def setUp(self):
        """Set up test models."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.account = helper.generate_aws_account(
            aws_account_id=aws_account_id, arn=arn, name="test"
        )

    @patch("api.models.notify_sources_application_availability")
    def test_delete_base_model_removes_platform_specific_model(
        self, mock_notify_sources
    ):
        """Deleting a generic model removes its more specific counterpart."""
        with patch.object(sts, "boto3") as mock_boto3, patch.object(
            aws_models, "_disable_cloudtrail"
        ):
            mock_assume_role = mock_boto3.client.return_value.assume_role
            mock_assume_role.return_value = self.role
            models.CloudAccount.objects.all().delete()
            self.assertEqual(0, models.CloudAccount.objects.count())
            self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
