"""Collection of tests for api.util.get_last_known_instance_type."""
import datetime

from django.test import TestCase

from api import util
from api.tests import helper as api_helper
from util.tests import helper as util_helper

one_hour = datetime.timedelta(hours=1)


class GetLastKnownInstanceTypeTest(TestCase):
    """Utility function 'get_last_known_instance_type' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        account = api_helper.generate_cloud_account()
        self.instance = api_helper.generate_instance(account)
        self.now = util.get_now()

    def test_type_found(self):
        """Test successfully getting the only defined instance type."""
        expected_instance_type = util_helper.get_random_instance_type()
        api_helper.generate_instance_events(
            self.instance, ((self.now - one_hour, None),), expected_instance_type
        )

        found_instance_type = util.get_last_known_instance_type(self.instance, self.now)

        self.assertEqual(found_instance_type, expected_instance_type)

    def test_type_found_most_recent(self):
        """Test successfully getting the most recent instance type."""
        old_instance_type = util_helper.get_random_instance_type()
        api_helper.generate_instance_events(
            self.instance, ((self.now - one_hour - one_hour, None),), old_instance_type
        )
        expected_instance_type = util_helper.get_random_instance_type(
            avoid=old_instance_type
        )
        api_helper.generate_instance_events(
            self.instance, ((self.now - one_hour, None),), expected_instance_type
        )

        found_instance_type = util.get_last_known_instance_type(self.instance, self.now)

        self.assertEqual(found_instance_type, expected_instance_type)

    def test_type_not_found(self):
        """Test not finding any instance type."""
        found_instance_type = util.get_last_known_instance_type(self.instance, self.now)
        self.assertIsNone(found_instance_type)
