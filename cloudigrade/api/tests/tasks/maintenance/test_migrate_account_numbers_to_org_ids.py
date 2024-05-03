"""Collection of tests for tasks.maintenance.delete_cloud_accounts_not_in_sources."""

import http
import json
from unittest.mock import patch

import faker
from django.test import TestCase, override_settings

from api.models import User
from api.tasks import maintenance
from util.tests import helper as util_helper

_faker = faker.Faker()


class MigrateAccountNumbersToOrgIdsTest(TestCase):
    """Migrate Account Numbers to Org Ids test case."""

    tenant_translator_scheme = "http"
    tenant_translator_host = "localhost"
    tenant_translator_port = "8892"
    tenant_translator_url = (
        f"{tenant_translator_scheme}://"
        f"{tenant_translator_host}:{tenant_translator_port}/"
        f"internal/orgIds"
    )

    @override_settings(TENANT_TRANSLATOR_SCHEME=tenant_translator_scheme)
    @override_settings(TENANT_TRANSLATOR_HOST=tenant_translator_host)
    @override_settings(TENANT_TRANSLATOR_PORT=tenant_translator_port)
    @patch("requests.post")
    def test_migrate_account_numbers_with_none_found(self, mock_post):
        """
        Test migrating account numbers with none found without an org_id.

        With no user objects without an org_id, this test should mention
        this in the log and do nothing.
        """
        util_helper.generate_test_user(org_id=util_helper.generate_org_id())
        util_helper.generate_test_user(org_id=util_helper.generate_org_id())

        with self.assertLogs("api.tasks.maintenance", level="INFO") as logging_watcher:
            maintenance.migrate_account_numbers_to_org_ids()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }

        expected_info_messages = [
            "There are no account_numbers without org_ids to migrate"
        ]

        for expected_info_message in expected_info_messages:
            self.assertIn(expected_info_message, info_messages)

    @override_settings(TENANT_TRANSLATOR_SCHEME=tenant_translator_scheme)
    @override_settings(TENANT_TRANSLATOR_HOST=tenant_translator_host)
    @override_settings(TENANT_TRANSLATOR_PORT=tenant_translator_port)
    @patch("requests.post")
    def test_migrate_account_numbers_with_no_org_ids(self, mock_post):
        """
        Test migrating account numbers with no org_ids.

        For Django user objects with no org_id,
        Query the tenant translation api and update the DB with the
        appropriate org_id's for those users.
        """
        user1 = util_helper.generate_test_user()
        util_helper.generate_test_user(org_id=util_helper.generate_org_id())
        user3 = util_helper.generate_test_user()

        user1_org_id = util_helper.generate_org_id()
        user3_org_id = util_helper.generate_org_id()

        expected_users_to_migrate = [user1.account_number, user3.account_number]

        with self.assertLogs("api.tasks.maintenance", level="INFO") as logging_watcher:
            mock_post.return_value.status_code = http.HTTPStatus.OK
            mock_post.return_value.json.return_value = {
                user1.account_number: user1_org_id,
                user3.account_number: user3_org_id,
            }
            maintenance.migrate_account_numbers_to_org_ids()

        info_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "INFO"
        }

        expected_info_messages = [
            f"Migrating {len(expected_users_to_migrate)} account_numbers to org_id",
            f"Calling tenant translator API {self.tenant_translator_url}",
            f"Migrated user account_number {user1.account_number}"
            f" to org_id {user1_org_id}",
            f"Migrated user account_number {user3.account_number}"
            f" to org_id {user3_org_id}",
        ]

        for expected_info_message in expected_info_messages:
            self.assertIn(expected_info_message, " ".join(info_messages))

        mock_post.assert_called_with(
            self.tenant_translator_url, data=json.dumps(expected_users_to_migrate)
        )

        updated_user1 = User.objects.filter(account_number=user1.account_number).get()
        updated_user3 = User.objects.filter(account_number=user3.account_number).get()

        self.assertEqual(updated_user1.org_id, user1_org_id)
        self.assertEqual(updated_user3.org_id, user3_org_id)

    @override_settings(TENANT_TRANSLATOR_SCHEME=tenant_translator_scheme)
    @override_settings(TENANT_TRANSLATOR_HOST=tenant_translator_host)
    @override_settings(TENANT_TRANSLATOR_PORT=tenant_translator_port)
    @patch("requests.post")
    def test_migrate_account_numbers_catches_exception(self, mock_post):
        """
        Test migrating account numbers catches exceptions.

        This test makes sure that the task properly catches exceptions
        during the migration and logs it accordingly.
        """
        user1 = util_helper.generate_test_user()

        expected_users_to_migrate = [user1.account_number]

        with self.assertLogs("api.tasks.maintenance", level="ERROR") as logging_watcher:
            mock_post.side_effect = Exception(
                "Error contacting the tenant translator API"
            )
            maintenance.migrate_account_numbers_to_org_ids()

        error_messages = {
            record.message
            for record in logging_watcher.records
            if record.levelname == "ERROR"
        }

        expected_error_message = (
            "Failed to migrate account_numbers to org_ids -"
            " Error contacting the tenant translator API"
        )

        mock_post.assert_called_with(
            self.tenant_translator_url, data=json.dumps(expected_users_to_migrate)
        )

        self.assertIn(expected_error_message, " ".join(error_messages))
