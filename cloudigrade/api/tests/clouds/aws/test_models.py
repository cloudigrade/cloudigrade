"""Collection of tests for custom Django model logic."""
import logging
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from django.test import TransactionTestCase

from api import models
from api.clouds.aws import models as aws_models
from api.tests import helper
from util.tests import helper as util_helper

logger = logging.getLogger(__name__)


class AwsCloudAccountModelTest(TransactionTestCase, helper.ModelStrTestMixin):
    """AwsCloudAccount Model Test Cases."""

    def setUp(self):
        """Set up basic aws account."""
        self.created_at = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        self.role = util_helper.generate_dummy_role()
        self.account = helper.generate_cloud_account(
            arn=arn,
            aws_account_id=aws_account_id,
            created_at=self.created_at,
        )

    def test_cloud_account_str(self):
        """Test that the CloudAccount str (and repr) is valid."""
        excluded_field_names = {"content_type", "object_id"}
        self.assertTypicalStrOutput(self.account, excluded_field_names)

    def test_aws_cloud_account_str(self):
        """Test that the AwsCloudAccount str (and repr) is valid."""
        self.assertTypicalStrOutput(self.account.content_object)

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_enable_succeeds(self, mock_notify_sources):
        """
        Test that enabling an account does all the relevant verification and setup.

        Disabling a CloudAccount having an AwsCloudAccount should:

        - set the CloudAccount.is_enabled to True
        - verify AWS IAM access and permissions
        - delay task to describe instances
        """
        # Normally you shouldn't directly manipulate the is_enabled value,
        # but here we need to force it down to check that it gets set back.
        self.account.is_enabled = False
        self.account.save()
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)

        enable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with patch(
            "api.clouds.aws.util.verify_permissions"
        ) as mock_verify_permissions, util_helper.clouditardis(enable_date):
            self.account.enable()
            mock_verify_permissions.assert_called()

        self.account.refresh_from_db()
        self.assertTrue(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, enable_date)

    def test_enable_failure(self):
        """Test that enabling an account rolls back if cloud-specific step fails."""
        # Normally you shouldn't directly manipulate the is_enabled value,
        # but here we need to force it down to check that it gets set back.
        self.account.is_enabled = False
        self.account.save()
        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

        with patch("api.clouds.aws.util.verify_permissions") as mock_verify_permissions:
            mock_verify_permissions.side_effect = Exception("Something broke.")
            with self.assertLogs("api.models", level="INFO") as cm:
                success = self.account.enable(disable_upon_failure=False)
                self.assertFalse(success)
            log_record = cm.records[1]
            self.assertEqual(
                str(mock_verify_permissions.side_effect), log_record.message
            )
            mock_verify_permissions.assert_called()

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_disable_succeeds(self, mock_notify_sources):
        """
        Test that disabling an account does all the relevant cleanup.

        Disabling a CloudAccount having an AwsCloudAccount should:

        - set the CloudAccount.is_enabled to False
        - disable the CloudTrail (via AwsCloudAccount.disable)
        """
        self.assertTrue(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.account.created_at)

        disable_date = util_helper.utc_dt(2019, 1, 4, 0, 0, 0)
        with util_helper.clouditardis(disable_date):
            with patch(
                "api.clouds.aws.util.delete_cloudtrail"
            ) as mock_delete_cloudtrail:
                mock_delete_cloudtrail.return_value = True
                self.account.disable()
                mock_delete_cloudtrail.assert_called()

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)
        self.assertEqual(self.account.enabled_at, self.created_at)

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_disable_with_notify_sources_false_succeeds(self, mock_notify_sources):
        """
        Test that disabling an account does not notify sources when specified not to.

        Setting notify_sources=False should *only* affect sources-api interactions.
        """
        self.assertTrue(self.account.is_enabled)
        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = True
            self.account.disable(notify_sources=False)
            mock_delete_cloudtrail.assert_called()
        mock_notify_sources.delay.assert_not_called()

        self.account.refresh_from_db()
        self.assertFalse(self.account.is_enabled)

    def test_disable_returns_early_if_account_is_enabled(self):
        """Test that AwsCloudAccount.disable returns early if is_enabled."""
        self.assertTrue(self.account.is_enabled)

        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = True
            self.account.content_object.disable()
            mock_delete_cloudtrail.assert_not_called()

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_succeeds(self, mock_notify_sources):
        """Test that an account is deleted if there are no errors."""
        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = True
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_succeeds_if_delete_cloudtrail_fails(self, mock_notify_sources):
        """Test that the account is deleted even if the CloudTrail is not disabled."""
        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = False
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    @patch("api.tasks.sources.notify_application_availability_task")
    @patch("api.clouds.aws.util.verify_permissions")
    def test_delete_cleans_up_related_objects(self, mock_verify, mock_notify_sources):
        """
        Verify that deleting an AWS account cleans up related objects.

        Deleting the account should also delete instances, events, runs, and the
        periodic verify task related to it.
        """
        self.account.enable()

        # First, verify that objects exist *before* deleting the AwsCloudAccount.
        self.assertGreater(aws_models.AwsCloudAccount.objects.count(), 0)
        self.assertGreater(models.CloudAccount.objects.count(), 0)

        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = True
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
        self.assertEqual(0, models.CloudAccount.objects.count())

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_via_queryset_succeeds_if_delete_cloudtrail_fails(
        self, mock_notify_sources
    ):
        """Account is deleted via queryset even if the CloudTrail is not disabled."""
        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = False
            aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_via_queryset_cleans_up_related_objects(self, mock_notify_sources):
        """Deleting an account via queryset cleans up related objects."""
        with patch("api.clouds.aws.util.delete_cloudtrail") as mock_delete_cloudtrail:
            mock_delete_cloudtrail.return_value = True
            aws_models.AwsCloudAccount.objects.all().delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
        self.assertEqual(0, models.CloudAccount.objects.count())

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_delete_account_when_aws_access_denied(self, mock_notify_sources):
        """
        Test that account deleted succeeds when AWS access is denied.

        This situation could happen when the customer removes IAM access before we
        delete the account instance.

        This test specifically exercises a fix for a bug where we would attempt and fail
        to load an object after it had been deleted, resulting in DoesNotExist being
        raised. See also:

        https://sentry.io/organizations/cloudigrade/issues/1744148258/?project=1270362
        """
        client_error = ClientError(
            error_response={"Error": {"Code": "AccessDenied"}},
            operation_name=Mock(),
        )
        with patch("api.clouds.aws.util.aws.get_session") as mock_get_session:
            mock_get_session.side_effect = client_error
            self.account.delete()
        self.assertEqual(0, aws_models.AwsCloudAccount.objects.count())
