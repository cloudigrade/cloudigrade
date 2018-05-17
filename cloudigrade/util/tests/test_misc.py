"""Collection of tests for ``util.misc`` module."""
from django.test import TestCase

from util.misc import generate_device_name


class UtilMiscTest(TestCase):
    """Misc utility functions test case."""

    def test_generate_device_name_success(self):
        """Assert that names are being properly generated."""
        self.assertEqual(generate_device_name(0), '/dev/xvdba')
        self.assertEqual(generate_device_name(1, '/dev/sd'), '/dev/sdbb')
