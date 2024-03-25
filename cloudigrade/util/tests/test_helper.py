"""Collection of tests for ``util.tests.helper`` module.

Because even test helpers should be tested!
"""

import datetime
import re

import faker
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.test import TestCase

from api.models import User
from util import aws
from util.tests import helper

_faker = faker.Faker()


class UtilHelperTest(TestCase):
    """Test helper functions test case."""

    def test_generate_dummy_aws_account_id(self):
        """Assert generation of an appropriate AWS AwsAccount ID."""
        account_id = str(helper.generate_dummy_aws_account_id())
        self.assertIsNotNone(re.match(r"\d{1,12}", account_id))

    def test_generate_dummy_arn_random_account_id(self):
        """Assert generation of an ARN without a specified account ID."""
        arn = helper.generate_dummy_arn()
        account_id = aws.AwsArn(arn).account_id
        self.assertIn(str(account_id), arn)

    def test_generate_dummy_arn_given_account_id(self):
        """Assert generation of an ARN with a specified account ID."""
        account_id = "012345678901"
        arn = helper.generate_dummy_arn(account_id)
        self.assertIn(account_id, arn)

    def test_generate_dummy_arn_given_resource(self):
        """Assert generation of an ARN with a specified resource."""
        resource = _faker.slug()
        arn = helper.generate_dummy_arn(resource=resource)
        self.assertTrue(arn.endswith(resource))

    def test_utc_dt(self):
        """Assert utc_dt adds timezone info."""
        d_no_tz = datetime.datetime(2018, 1, 1)
        d_helped = helper.utc_dt(2018, 1, 1)
        self.assertNotEqual(d_helped, d_no_tz)
        self.assertIsNotNone(d_helped.tzinfo)

    def test_generate_test_user(self):
        """Assert generation of test user with appropriate defaults."""
        user = helper.generate_test_user()
        self.assertFalse(user.is_superuser)
        other_user = helper.generate_test_user()
        self.assertNotEqual(user, other_user)
        self.assertNotEqual(user.account_number, other_user.account_number)

    def test_generate_test_user_with_args(self):
        """Assert generation of test user with specified arguments."""
        account_number = _faker.random_int(min=100000, max=999999)
        date_joined = helper.utc_dt(2017, 12, 11, 8, 0, 0)
        user = helper.generate_test_user(
            account_number=account_number, is_superuser=True, date_joined=date_joined
        )
        self.assertEqual(user.account_number, account_number)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.date_joined, date_joined)

    def test_get_test_user_creates(self):
        """Assert get_test_user creates a user when it doesn't yet exist."""
        user = helper.get_test_user()
        self.assertIsNotNone(user)

    def test_get_test_user_updates_without_password(self):
        """Assert get_test_user gets and updates user if found."""
        account_number = _faker.random_int(min=100000, max=999999)
        original_user = User.objects.create_user(account_number)
        user = helper.get_test_user(account_number, is_superuser=True)
        original_user.refresh_from_db()
        self.assertEqual(user, original_user)
        self.assertTrue(user.is_superuser)

    def test_get_test_user_updates_with_password(self):
        """Assert get_test_user updates user with password if found."""
        account_number = _faker.random_int(min=100000, max=999999)
        password = _faker.uuid4()
        original_user = User.objects.create_user(account_number)
        user = helper.get_test_user(account_number, password)
        original_user.refresh_from_db()
        self.assertEqual(user, original_user)
        self.assertTrue(user.check_password(password))

    def test_clouditardis(self):
        """Assert that clouditardis breaks the space-time continuum."""
        the_present_time = datetime.datetime.now(datetime.timezone.utc)
        the_present_date = the_present_time.date()

        the_day_i_invented_time_travel = helper.utc_dt(1955, 11, 5, 4, 29)
        with helper.clouditardis(the_day_i_invented_time_travel):
            # local imports to simulate tests
            from util.misc import get_now as _get_now, get_today as _get_today

            the_past_time = _get_now()
            the_past_date = _get_today()

        self.assertLess(the_past_time, the_present_time)
        self.assertLess(the_past_date, the_present_date)

    def test_mock_signal_handler(self):
        """Assert mock_signal_handler temporarily bypasses original signal handler."""

        class OriginalHandlerWasCalled(Exception):
            """Raise to identify when the original signal handler is called."""

        @receiver(post_save, sender=User)
        def _handler(*args, **kwargs):
            """Raise exception to indicate the handler was called."""
            raise OriginalHandlerWasCalled

        with helper.mock_signal_handler(post_save, _handler, User) as mock_handler:
            # OriginalHandlerWasCalled should not be raised because _handler is mocked.
            User.objects.create_user(_faker.name())
            mock_handler.assert_called_once()

        with self.assertRaises(OriginalHandlerWasCalled):
            User.objects.create_user(_faker.name())
