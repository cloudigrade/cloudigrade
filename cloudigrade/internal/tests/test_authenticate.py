"""Collection of tests targeting custom internal authentication modules."""
from unittest.mock import Mock

import faker
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase

from internal.authentication import (
    IdentityHeaderAuthenticationInternal,
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
        self.assertEqual(self.account_number, user.username)

    def test_authenticate_not_admin(self):
        """Test that authentication header without org admin user succeeds."""
        request = Mock()
        request.META = {settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_not_admin}

        user, auth = self.auth_class.authenticate(request)

        self.assertTrue(auth)
        self.assertEqual(self.account_number, user.username)

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
        self.rh_header_as_admin_not_found = util_helper.get_identity_auth_header(
            account_number=self.account_number_not_found
        )
        self.auth_class = IdentityHeaderAuthenticationInternalCreateUser()

    def test_authenticate_no_user(self):
        """Test that authentication creates a user for auth if it does not exist."""
        request = Mock()
        request.META = {
            settings.INSIGHTS_IDENTITY_HEADER: self.rh_header_as_admin_not_found
        }
        user, auth = self.auth_class.authenticate(request)
        self.assertEqual(user.username, self.account_number_not_found)
        self.assertEqual(user, User.objects.get(username=self.account_number_not_found))
