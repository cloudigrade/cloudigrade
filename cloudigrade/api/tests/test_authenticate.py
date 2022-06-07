"""Collection of tests targeting custom authentication modules."""
import base64
import json
from unittest.mock import Mock

import faker
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.authentication import exceptions

from api.authentication import (
    IdentityHeaderAuthentication,
    IdentityHeaderAuthenticationUserNotRequired,
    get_or_create_user,
    get_user_by_account,
    parse_insights_request_id,
)
from api.models import User
from util.tests import helper as util_helper

_faker = faker.Faker()


class PskHeaderAuthenticateTestCase(TestCase):
    """Test that PSK header authentication works as expected."""

    def setUp(self):
        """Set up data for tests."""
        self.insights_request_id = _faker.uuid4().replace("-", "")
        self.account_number = str(_faker.pyint())
        self.account_number_not_found = str(_faker.pyint())
        self.org_id = str(_faker.pyint())
        self.user = util_helper.generate_test_user(
            self.account_number, org_id=self.org_id
        )
        self.valid_svc_psk = _faker.uuid4()
        self.valid_svc_name = _faker.slug()
        self.invalid_svc_psk = _faker.uuid4()
        self.cloudigrade_psks = {self.valid_svc_name: self.valid_svc_psk}
        self.auth_class = IdentityHeaderAuthentication()

    def test_parse_insights_request_id(self):
        """Make sure the Insights Id of the authenticated request is logged."""
        request = Mock()
        request.META = {settings.INSIGHTS_REQUEST_ID_HEADER: self.insights_request_id}
        with self.assertLogs("api.authentication", level="INFO") as logging_watcher:
            parse_insights_request_id(request)
            self.assertIn(
                "Authenticating via insights, INSIGHTS_REQUEST_ID: "
                + self.insights_request_id,
                logging_watcher.output[0],
            )

    def test_get_user_with_missing_account_number(self):
        """Test that get_user with a missing account number returns None."""
        self.assertIsNone(
            IdentityHeaderAuthentication.get_user(self.auth_class, None, None)
        )

    def test_get_user_with_org_id(self):
        """Test that get_user with org_id returns the user."""
        self.assertEqual(
            IdentityHeaderAuthentication.get_user(self.auth_class, None, self.org_id),
            self.user,
        )

    def test_authenticate(self):
        """Test that authentication with the correct PSK and account header succeeds."""
        request = Mock()
        request.META = {
            settings.CLOUDIGRADE_PSK_HEADER: self.valid_svc_psk,
            settings.CLOUDIGRADE_ACCOUNT_NUMBER_HEADER: self.account_number,
        }

        with override_settings(CLOUDIGRADE_PSKS=self.cloudigrade_psks):
            user, auth = self.auth_class.authenticate(request)

            self.assertTrue(auth)
            self.assertEqual(self.account_number, user.account_number)
            self.assertEqual(user, self.user)

    def test_authenticate_with_org_id(self):
        """Test that authentication with the correct PSK and org_id header succeeds."""
        request = Mock()
        request.META = {
            settings.CLOUDIGRADE_PSK_HEADER: self.valid_svc_psk,
            settings.CLOUDIGRADE_ORG_ID_HEADER: self.org_id,
        }

        with override_settings(CLOUDIGRADE_PSKS=self.cloudigrade_psks):
            user, auth = self.auth_class.authenticate(request)

            self.assertTrue(auth)
            self.assertEqual(self.org_id, user.org_id)
            self.assertEqual(user, self.user)

    def test_authenticate_with_invalid_psk(self):
        """Test that authentication with an invalid PSK header fails."""
        request = Mock()
        request.META = {
            settings.CLOUDIGRADE_PSK_HEADER: self.invalid_svc_psk,
            settings.CLOUDIGRADE_ACCOUNT_NUMBER_HEADER: self.account_number,
        }

        with override_settings(CLOUDIGRADE_PSKS=self.cloudigrade_psks):
            with self.assertLogs("api.authentication", level="INFO") as logging_watcher:
                with self.assertRaises(exceptions.AuthenticationFailed):
                    self.auth_class.authenticate(request)
                self.assertIn(
                    "Authentication Failed: Invalid PSK '"
                    + self.invalid_svc_psk
                    + "' specified in header",
                    logging_watcher.output[1],
                )

    def test_authenticate_with_missing_account_number(self):
        """Test that PSK authentication with a missing account number fails."""
        request = Mock()
        request.META = {
            settings.CLOUDIGRADE_PSK_HEADER: self.valid_svc_psk,
        }

        with override_settings(CLOUDIGRADE_PSKS=self.cloudigrade_psks):
            with self.assertLogs("api.authentication", level="INFO") as logging_watcher:
                with self.assertRaises(exceptions.AuthenticationFailed):
                    self.auth_class.authenticate(request)
                self.assertIn(
                    "PSK header for service '"
                    + self.valid_svc_name
                    + "' with no account_number or org_id",
                    logging_watcher.output[1],
                )


class IdentityHeaderAuthenticateTestCase(TestCase):
    """
    Test that identity header authentication works as expected.

    When a request for a v2 endpoint comes in, we expect a base64 encoded
    HTTP_X_RH_IDENTITY header containing JSON. When this header exists, we use the
    JSON's identity's account number as the value to find a User's account_number
    for our authentication.
    """

    def setUp(self):
        """Set up data for tests."""
        self.account_number = str(_faker.pyint())
        self.account_number_not_found = str(_faker.pyint())
        self.org_id = str(_faker.pyint())
        self.user = util_helper.generate_test_user(
            self.account_number, org_id=self.org_id
        )
        self.rh_header_as_admin = util_helper.get_identity_auth_header(
            account_number=self.account_number
        )
        self.rh_header_no_account_number = util_helper.get_identity_auth_header(
            account_number=None
        )
        self.rh_header_not_admin = util_helper.get_identity_auth_header(
            account_number=self.account_number, is_org_admin=False
        )
        self.rh_header_as_admin_not_found = util_helper.get_identity_auth_header(
            account_number=self.account_number_not_found
        )
        self.rh_header_as_admin_with_org_id = util_helper.get_identity_auth_header(
            account_number=self.account_number, org_id=self.org_id
        )
        self.auth_class = IdentityHeaderAuthentication()

    def test_authenticate(self):
        """Test that authentication with the correct header succeeds."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin}

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.account_number)
        self.assertEqual(user, self.user)

    def test_authenticate_with_account_number_and_org_id(self):
        """Test that authentication with both account_number and org_id succeeds."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin_with_org_id
        }

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.account_number)
        self.assertEqual(self.org_id, user.org_id)
        self.assertEqual(user, self.user)

    def test_authenticate_with_verbose_logging(self):
        """Test that valid authentication logs the decoded header."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin}

        with override_settings(VERBOSE_INSIGHTS_IDENTITY_HEADER_LOGGING=True):
            with self.assertLogs("api.authentication", level="INFO") as logging_watcher:
                user, auth = self.auth_class.authenticate(request)

                self.assertTrue(auth)
                self.assertEqual(self.account_number, user.account_number)
                self.assertIn("Decoded identity header: ", logging_watcher.output[1])

    def test_authenticate_not_org_admin_fails(self):
        """Test that header without org admin user fails."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_not_admin}

        with self.assertRaises(exceptions.PermissionDenied) as e:
            self.auth_class.authenticate(request)
        self.assertIn("User must be an org admin", e.exception.args[0])

    def test_authenticate_bad_b64_padding(self):
        """Test authentication fails when the identity header has bad b64 padding."""
        bad_rh_header = "111"  # This string triggers binascii.Error in b64decode.

        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: bad_rh_header}

        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.auth_class.authenticate(request)
        self.assertIn("Authentication Failed", e.exception.args[0])

    def test_authenticate_not_json_header_fails(self):
        """Test that authentication fails when the identity header is invalid JSON."""
        bad_rh_header = base64.b64encode(b"Not JSON")

        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: bad_rh_header}

        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.auth_class.authenticate(request)
        self.assertIn("Authentication Failed", e.exception.args[0])

    def test_authenticate_incomplete_header_fails(self):
        """Test that authentication fails when the identity header is incomplete."""
        rh_identity = {"user": {"email": self.account_number}}
        bad_rh_header = base64.b64encode(json.dumps(rh_identity).encode("utf-8"))

        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: bad_rh_header}

        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.auth_class.authenticate(request)
        self.assertIn("Authentication Failed", e.exception.args[0])

    def test_authenticate_no_header_fails(self):
        """Test that authentication fails when given no headers."""
        request = Mock()
        request.META = {}

        with self.assertRaises(exceptions.AuthenticationFailed):
            self.auth_class.authenticate(request)

    def test_authenticate_no_account_number_fails(self):
        """Test that permission is denied when identity has no account number."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_no_account_number
        }

        with self.assertRaises(exceptions.AuthenticationFailed):
            self.auth_class.authenticate(request)

    def test_authenticate_no_user_fails(self):
        """Test that authentication fails when a matching User cannot be found."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin_not_found
        }

        with self.assertRaises(exceptions.AuthenticationFailed):
            self.auth_class.authenticate(request)

        users = User.objects.all()
        self.assertEqual(1, len(users))
        self.assertEqual(self.user, users[0])


class IdentityHeaderAuthenticationUserNotRequiredTestCase(TestCase):
    """
    Test that identity header authentication works as expected.

    Unlike IdentityHeaderAuthentication, presence of a matching User is not hard
    requirement for this authentication class.
    """

    def setUp(self):
        """Set up data for tests."""
        self.account_number_no_user = str(_faker.pyint())
        self.rh_header_as_admin_no_user = util_helper.get_identity_auth_header(
            account_number=self.account_number_no_user
        )
        self.rh_header_no_account_number = util_helper.get_identity_auth_header(
            account_number=None
        )
        self.auth_class = IdentityHeaderAuthenticationUserNotRequired()

    def test_authenticate_account_number_but_no_user(self):
        """
        Test that authentication with account number but no user proceeds normally.

        Note that this does not mean that there is a real successful authentication
        because that would mean returning a User. This just means that we quietly
        proceed without blowing up an authentication-related error to user user.
        """
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin_no_user
        }

        result = self.auth_class.authenticate(request)
        self.assertIsNone(result)

    def test_authenticate_no_account_number(self):
        """Test that authentication fails when header has no account number."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_no_account_number
        }

        with self.assertRaises(exceptions.AuthenticationFailed):
            self.auth_class.authenticate(request)


class GetUserByAccountMethodTests(TestCase):
    """Tests to verify the right user objects are returned."""

    def setUp(self):
        """Set up data for tests."""
        self.user1_account_number = str(_faker.pyint())
        self.user1_org_id = str(_faker.pyint())
        self.user1 = util_helper.generate_test_user(
            account_number=self.user1_account_number, org_id=self.user1_org_id
        )
        self.user2_account_number = str(_faker.pyint())
        self.user2 = util_helper.generate_test_user(
            account_number=self.user2_account_number, org_id=None
        )
        self.user3_org_id = str(_faker.pyint())
        self.user3 = util_helper.generate_test_user(
            account_number=None, org_id=self.user3_org_id
        )

    def test_user_with_account_number_and_org_id(self):
        """Test to search user object by account_number and org_id."""
        user = get_user_by_account(
            account_number=self.user1_account_number, org_id=self.user1_org_id
        )
        self.assertEqual(user, self.user1)

    def test_user_with_account_number(self):
        """Test to search user object by account_number."""
        user = get_user_by_account(
            account_number=self.user2_account_number,
            org_id=None,
        )
        self.assertEqual(user, self.user2)

    def test_user_with_org_id(self):
        """Test to search user object by org_id."""
        user = get_user_by_account(
            account_number=None,
            org_id=self.user3_org_id,
        )
        self.assertEqual(user, self.user3)


class GetOrCreateUserMethodTests(TestCase):
    """Tests to verify the right user objects are obtained or created."""

    def setUp(self):
        """Set up data for tests."""
        self.user1_account_number = str(_faker.pyint())
        self.user1_org_id = str(_faker.pyint())
        self.user1 = util_helper.generate_test_user(
            account_number=self.user1_account_number, org_id=self.user1_org_id
        )
        self.user2_account_number = str(_faker.pyint())
        self.user2 = util_helper.generate_test_user(
            account_number=self.user2_account_number, org_id=None
        )
        self.user3_org_id = str(_faker.pyint())
        self.user3 = util_helper.generate_test_user(
            account_number=None, org_id=self.user3_org_id
        )

    def test_get_with_account_number_and_org_id(self):
        """Test to get user object by account_number and org_id."""
        user = get_or_create_user(
            account_number=self.user1_account_number, org_id=self.user1_org_id
        )
        self.assertEqual(user, self.user1)

    def test_get_with_account_number(self):
        """Test to get user object by account_number."""
        user = get_or_create_user(account_number=self.user2_account_number, org_id=None)
        self.assertEqual(user, self.user2)

    def test_get_with_org_id(self):
        """Test to get user object by org_id."""
        user = get_or_create_user(account_number=None, org_id=self.user3_org_id)
        self.assertEqual(user, self.user3)

    def test_create_with_org_id(self):
        """Test to create user object by org_id."""
        new_org_id = str(_faker.pyint())
        user = get_or_create_user(account_number=None, org_id=new_org_id)
        self.assertIsNone(user.account_number)
        self.assertEqual(user.org_id, new_org_id)
