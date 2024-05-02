"""Collection of tests for ``account.tests.helper`` module.

Because even test helpers should be tested!
"""

import http
import re
from unittest.mock import patch

import faker
from django.test import TestCase

from api.models import CloudAccount
from api.tests import helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class SandboxedRestClientTest(TestCase):
    """SandboxedRestClient tests."""

    def setUp(self):
        """Set up user for the client tests."""
        self.account_number = _faker.random_int(min=100000, max=999999)
        self.org_id = _faker.random_int(min=100000, max=999999)
        self.password = _faker.slug()
        self.user = util_helper.generate_test_user(
            account_number=self.account_number,
            org_id=self.org_id,
            password=self.password,
        )
        self.x_rh_identity = util_helper.get_identity_auth_header(
            self.account_number
        ).decode("utf-8")

    def test_list_noun(self):
        """Assert "list" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(
            self.user, {"HTTP_X_RH_IDENTITY": self.x_rh_identity}
        )
        response = client.list_accounts()
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        response_json = response.json()
        self.assertIn("data", response_json)
        self.assertIsInstance(response_json["data"], list)
        self.assertIn("meta", response_json)
        self.assertIn("count", response_json["meta"])
        self.assertIn("links", response_json)
        self.assertIn("next", response_json["links"])
        self.assertIn("previous", response_json["links"])
        self.assertIn("first", response_json["links"])
        self.assertIn("last", response_json["links"])

    @patch("api.tasks.sources.notify_application_availability_task")
    def test_create_noun(self, mock_notify_sources):
        """Assert "create" requests work."""
        client = helper.SandboxedRestClient(api_root="/internal/api/cloudigrade/v1")
        client._force_authenticate(
            self.user, {"HTTP_X_RH_IDENTITY": self.x_rh_identity}
        )
        arn = util_helper.generate_dummy_arn()
        data = util_helper.generate_dummy_aws_cloud_account_post_data()
        data.update({"account_arn": arn})
        response = client.create_accounts(data=data)
        self.assertEqual(response.status_code, http.HTTPStatus.CREATED)
        response_json = response.json()
        self.assertEqual(response_json["content_object"]["account_arn"], arn)
        self.assertEqual(response_json["user_id"], self.user.id)

    def test_get_noun(self):
        """Assert "get" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(
            self.user, {"HTTP_X_RH_IDENTITY": self.x_rh_identity}
        )
        account = helper.generate_cloud_account(user=self.user)
        response = client.get_accounts(account.id)
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        response_json = response.json()
        self.assertEqual(response_json["account_id"], account.id)

    def test_invalid_request(self):
        """Assert invalid requests raise AttributeError."""
        client = helper.SandboxedRestClient()
        with self.assertRaises(AttributeError):
            client.foo_bar()


class GenerateCloudAccountTest(TestCase):
    """generate_cloud_account tests."""

    def test_generate_aws_account_default(self):
        """Assert generation of an AwsAccount with default/no args."""
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        with util_helper.clouditardis(created_at):
            account = helper.generate_cloud_account()
        self.assertIsInstance(account, CloudAccount)
        self.assertIsNotNone(
            re.match(r"\d{1,12}", str(account.content_object.aws_account_id))
        )
        self.assertEqual(account.created_at, created_at)
        self.assertTrue(account.is_enabled)
        self.assertEqual(account.enabled_at, created_at)
        self.assertIsNotNone(account.platform_authentication_id)
        self.assertIsNotNone(account.platform_application_id)
        self.assertFalse(account.platform_application_is_paused)
        self.assertIsNotNone(account.platform_source_id)

    def test_generate_azure_account_default(self):
        """Assert generation of an AzureAccount with default/no args."""
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        with util_helper.clouditardis(created_at):
            account = helper.generate_cloud_account(cloud_type="azure")
        self.assertIsInstance(account, CloudAccount)
        self.assertIsNotNone(account.content_object.subscription_id)
        self.assertEqual(account.created_at, created_at)
        self.assertTrue(account.is_enabled)
        self.assertEqual(account.enabled_at, created_at)
        self.assertIsNotNone(account.platform_authentication_id)
        self.assertIsNotNone(account.platform_application_id)
        self.assertFalse(account.platform_application_is_paused)
        self.assertIsNotNone(account.platform_source_id)

    def test_generate_aws_account_with_args(self):
        """Assert generation of an AwsAccount with all specified args."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        user = util_helper.generate_test_user()
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        platform_authentication_id = _faker.pyint()
        platform_application_id = _faker.pyint()
        platform_source_id = _faker.pyint()
        is_enabled = False
        enabled_at = util_helper.utc_dt(2017, 1, 2, 0, 0, 0)

        account = helper.generate_cloud_account(
            arn=arn,
            aws_account_id=aws_account_id,
            user=user,
            created_at=created_at,
            platform_authentication_id=platform_authentication_id,
            platform_application_id=platform_application_id,
            platform_application_is_paused=True,
            platform_source_id=platform_source_id,
            is_enabled=is_enabled,
            enabled_at=enabled_at,
        )
        self.assertIsInstance(account, CloudAccount)
        self.assertEqual(account.content_object.account_arn, arn)
        self.assertEqual(account.content_object.aws_account_id, aws_account_id)

        self.assertEqual(account.platform_authentication_id, platform_authentication_id)
        self.assertEqual(account.platform_application_id, platform_application_id)
        self.assertTrue(account.platform_application_is_paused)
        self.assertEqual(account.platform_source_id, platform_source_id)
        self.assertEqual(account.user, user)
        self.assertEqual(account.created_at, created_at)
        self.assertFalse(account.is_enabled)
        self.assertEqual(account.enabled_at, enabled_at)

    def test_generate_aws_account_missing_content_object(self):
        """Assert generation of an AwsAccount with missing content object."""
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        with util_helper.clouditardis(created_at):
            account = helper.generate_cloud_account(
                cloud_type="aws", missing_content_object=True
            )
        self.assertIsInstance(account, CloudAccount)
        self.assertIsNone(account.content_object)
