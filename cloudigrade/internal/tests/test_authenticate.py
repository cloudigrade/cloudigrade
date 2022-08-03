"""Collection of tests targeting custom internal authentication modules."""
from unittest.mock import Mock

import faker
from django.conf import settings
from django.test import TestCase
from rest_framework.authentication import exceptions

from api.models import User
from internal.authentication import (
    IdentityHeaderAuthenticationInternal,
    IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader,
    IdentityHeaderAuthenticationInternalCreateUser,
)
from util.tests import helper as util_helper

_faker = faker.Faker()


class IdentityHeaderAuthenticationInternalTestCase(TestCase):
    """
    Test that identity header authentication works as expected.

    Unlike IdentityHeaderAuthentication, org admin in the header identity and the
    presence of a matching User are not hard requirements for this authentication class.
    """

    def setUp(self):
        """Set up data for tests."""
        self.account_number = str(_faker.pyint())
        self.account_number_not_found = str(_faker.pyint())

        self.user = util_helper.generate_test_user(self.account_number)
        self.rh_header_as_admin = util_helper.get_identity_auth_header(
            account_number=self.account_number
        )
        self.rh_header_not_admin = util_helper.get_identity_auth_header(
            account_number=self.account_number, is_org_admin=False
        )
        self.rh_header_as_admin_not_found = util_helper.get_identity_auth_header(
            account_number=self.account_number_not_found
        )
        self.auth_class = IdentityHeaderAuthenticationInternal()

    def test_authenticate(self):
        """Test that authentication with the correct header succeeds."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin}

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.account_number)

    def test_authenticate_not_admin(self):
        """Test that authentication header without org admin user succeeds."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_not_admin}

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.account_number)

    def test_authenticate_no_user(self):
        """Test that authentication returns None when user does not exist."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin_not_found
        }
        result = self.auth_class.authenticate(request)
        self.assertIsNone(result)


class IdentityHeaderAuthenticationInternalCreateUserTestCase(TestCase):
    """
    Test that identity header authentication with user creation works as expected.

    Unlike IdentityHeaderAuthenticationInternal, a User will be created if it doesn't
    exist.
    """

    def setUp(self):
        """Set up data for tests."""
        self.account_number_not_found = str(_faker.pyint())
        self.org_id_not_found = str(_faker.pyint())
        self.rh_header_as_admin_not_found = util_helper.get_identity_auth_header(
            account_number=self.account_number_not_found
        )
        self.rh_header_with_org_id_not_found = util_helper.get_identity_auth_header(
            account_number=self.account_number_not_found,
            org_id=self.org_id_not_found,
        )
        self.auth_class = IdentityHeaderAuthenticationInternalCreateUser()

    def test_authenticate_no_user(self):
        """Test that authentication creates a user for auth if it does not exist."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin_not_found
        }
        user, auth = self.auth_class.authenticate(request)
        self.assertEqual(user.account_number, self.account_number_not_found)
        self.assertEqual(
            user, User.objects.get(account_number=self.account_number_not_found)
        )

    def test_authenticate_no_user_with_org_id(self):
        """Test that authentication creates a user for auth if it does not exist."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_with_org_id_not_found
        }
        user, auth = self.auth_class.authenticate(request)
        self.assertEqual(user.account_number, self.account_number_not_found)
        self.assertEqual(user.org_id, self.org_id_not_found)
        self.assertEqual(
            user,
            User.objects.get(
                account_number=self.account_number_not_found,
                org_id=self.org_id_not_found,
            ),
        )


class IdentityHeaderAuthenticationInternalConcurrentCase(TestCase):
    """
    Test that an associate Internal header authentication works as expected.

    When a request for a v2 endpoint comes in, internal API calls may come in
    with an HTTP_X_RH_IDENTITY representing an associate that would not include
    the account number or is_org_admin flag. These tests verify the expected
    behaviors as well as handling the optional HTTP_X_RH_IDENTITY_ACCOUNT
    and HTTP_X_RH_IDENTITY_ORG_ADMIN headers.
    """

    def setUp(self):
        """Set up data for tests."""
        self.account_number = str(_faker.pyint())
        self.account_number_not_found = str(_faker.pyint())
        self.user = util_helper.generate_test_user(self.account_number)
        self.internal_rh_header = util_helper.get_internal_identity_auth_header()
        self.auth_class = IdentityHeaderAuthenticationInternalAllowFakeIdentityHeader()

    def test_authenticate(self):
        """Test that authentication with just the default internal header fails."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.internal_rh_header}
        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.auth_class.authenticate(request)
        self.assertIn(
            "identity account number or org id is required, but neither"
            " is present in request.",
            str(e.exception),
        )

    def test_authenticate_with_valid_account_number_and_not_org_admin_fake_header(self):
        """Test authentication with valid account_number but no org admin succeeds."""
        request = Mock()
        fake_header = util_helper.get_identity_auth_header(
            account_number=self.account_number,
            is_org_admin=False,
        )
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.internal_rh_header,
            settings.INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER: fake_header,
        }

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.account_number)

    def test_authenticate_with_invalid_account_number_and_org_admin_fake_header(self):
        """Test authentication with invalid account_number and org admin fails."""
        request = Mock()
        fake_header = util_helper.get_identity_auth_header(
            account_number=str(_faker.pyint()),
            is_org_admin=True,
        )
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.internal_rh_header,
            settings.INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER: fake_header,
        }
        with self.assertRaises(exceptions.AuthenticationFailed) as e:
            self.auth_class.authenticate(request)
        self.assertIn("Incorrect authentication credentials.", str(e.exception))

    def test_authenticate_with_invalid_account_number_and_not_org_admin_fake_header(
        self,
    ):
        """Test authentication with invalid account_number and org admin fails."""
        request = Mock()
        fake_header = util_helper.get_identity_auth_header(
            account_number=str(_faker.pyint()),
            is_org_admin=False,
        )
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.internal_rh_header,
            settings.INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER: fake_header,
        }
        with self.assertRaises(exceptions.AuthenticationFailed):
            self.auth_class.authenticate(request)

    def test_authenticate_with_valid_account_number_and_org_admin_headers(self):
        """Test authentication with valid account_number and org admin succeeds."""
        request = Mock()
        fake_header = util_helper.get_identity_auth_header(
            account_number=self.account_number,
            is_org_admin=True,
        )
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.internal_rh_header,
            settings.INSIGHTS_INTERNAL_FAKE_IDENTITY_HEADER: fake_header,
        }

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.account_number)
