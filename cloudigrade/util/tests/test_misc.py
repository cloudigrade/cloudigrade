"""Collection of tests for ``util.misc`` module."""
from datetime import datetime, timedelta
from unittest.mock import patch

from dateutil import tz
from django.test import TestCase

from util import misc
from util.misc import generate_device_name


class UtilMiscTest(TestCase):
    """Misc utility functions test case."""

    def test_generate_device_name_success(self):
        """Assert that names are being properly generated."""
        self.assertEqual(generate_device_name(0), "/dev/xvdba")
        self.assertEqual(generate_device_name(1, "/dev/sd"), "/dev/sdbb")

    def test_truncate_date_return_original(self):
        """Assert we allow values from the past."""
        yesterday = datetime.now(tz=tz.tzutc()) - timedelta(days=1)
        output = misc.truncate_date(yesterday)
        self.assertEqual(output, yesterday)

    def test_truncate_date_return_now(self):
        """Assert we truncate future dates to "now"."""
        now = datetime.now(tz=tz.tzutc())
        tomorrow = now + timedelta(days=1)
        with patch.object(misc, "datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = now
            output = misc.truncate_date(tomorrow)
        self.assertEqual(output, now)
