"""Collection of tests for ``util.redhatcloud.identity`` module."""
import re

import faker
from django.test import TestCase, override_settings

from util.redhatcloud import psk

_faker = faker.Faker()


class PskTest(TestCase):
    """Red Hat Cloud PSK module test case."""

    def fake_svc_name(self):
        """Generate a fake service name."""
        return _faker.slug().lower()

    def fake_svc_psk(self):
        """Generate a fake service PSK."""
        return _faker.hexify(text="^^^^^^^^-^^^^^^^^-^^^^^^^^-^^^^^^^^")

    def fake_svc_entry(self, svc_name=None, svc_psk=None):
        """Generate a fake service entry."""
        name = svc_name or self.fake_svc_name()
        psk = svc_psk or self.fake_svc_psk()
        return name + ":" + psk

    def setUp(self):
        """Set up test data."""
        self.svc_name = self.fake_svc_name()
        self.svc_psk = self.fake_svc_psk()
        self.svc_entry = self.fake_svc_entry(self.svc_name, self.svc_psk)

    def test_normalize_service_name_lc(self):
        """Assert normalization of a service name to lower case."""
        self.assertEqual("myservicename", psk.normalize_service_name("MyServiceName"))

    def test_normalize_service_name_lc_with_comma(self):
        """Assert normalization of a service name with commas."""
        self.assertEqual(
            "my-service-name", psk.normalize_service_name("My,Service,Name")
        )

    def test_normalize_service_name_lc_with_colon(self):
        """Assert normalization of a service name with colons."""
        self.assertEqual(
            "my-service-name", psk.normalize_service_name("My:Service:Name")
        )

    def test_normalize_service_name_lc_with_comma_and_colon(self):
        """Assert normalization of a service name with commas and colons."""
        self.assertEqual(
            "my-service-name", psk.normalize_service_name("My,Service:Name")
        )

    def test_normalize_service_name_lc_with_commas_and_colons(self):
        """Assert normalization of a service name with multiple commas and colons."""
        self.assertEqual(
            "my-super-service-name",
            psk.normalize_service_name("My,:SUPER,,Service:,:Name"),
        )

    def test_service_entry(self):
        """Assert service entry returns the properly formed service-name:service-psk."""
        expected = self.svc_name + ":" + self.svc_psk
        self.assertEqual(expected, psk.service_entry(self.svc_name, self.svc_psk))

    def test_service_entry_normalizes_service_name(self):
        """Assert service entry returns the normalized service-name:service-psk."""
        nonstd_name = "NonStd-Name"
        expected = "nonstd-name:" + self.svc_psk
        self.assertEqual(expected, psk.service_entry(nonstd_name, self.svc_psk))

    def test_service_entry_normalizes_service_name_and_keeps_psk(self):
        """Assert service entry returns the normalized name and PSK as is."""
        nonstd_name = "NonStd-Name"
        nonstd_psk = "NON_STANDARD_PSK"
        expected = nonstd_name.lower() + ":" + nonstd_psk
        self.assertEqual(expected, psk.service_entry(nonstd_name, nonstd_psk))

    def test_psk_service_name(self):
        """Assert psk_service_name returns the svc_name for the PSK specified."""
        svc_name = self.fake_svc_name()
        svc_psk = self.fake_svc_psk()
        cloudigrade_psks = ("{},{},{},{}:{},{}").format(
            self.fake_svc_entry(),
            self.fake_svc_entry(),
            self.fake_svc_entry(),
            svc_name,
            svc_psk,
            self.fake_svc_entry(),
        )

        with override_settings(CLOUDIGRADE_PSKS=cloudigrade_psks):
            self.assertEqual(svc_name, psk.psk_service_name(svc_psk))

    def test_psk_service_name_returns_none(self):
        """Assert psk_service_name returns None for no match."""
        svc_psk = self.fake_svc_psk()
        cloudigrade_psks = self.fake_svc_entry() + "," + self.fake_svc_entry()
        with override_settings(CLOUDIGRADE_PSKS=cloudigrade_psks):
            self.assertEqual(None, psk.psk_service_name(svc_psk))

    def test_generate_psk(self):
        """Assert generate_psk returns a properly formed PSK."""
        expected_pattern = "^[a-z0-9]{8}-[a-z0-9]{8}-[a-z0-9]{8}-[a-z0-9]{8}$"
        match = re.match(expected_pattern, psk.generate_psk())
        self.assertIsNotNone(match)

    def test_add_service_psk_on_empty_psks_list(self):
        """Assert add_service_psk returns just the new entry with an empty psks list."""
        self.assertEqual(
            self.svc_entry, psk.add_service_psk("", self.svc_name, self.svc_psk)
        )

    def test_add_service_psk(self):
        """Assert add_service_psk adds the psk in sorted order."""
        new_name = "b-service"
        new_psk = "0202"
        current_psks = "a-service:0101,c-service:0303"
        expected_psks = ("a-service:0101,{},c-service:0303").format(
            self.fake_svc_entry(new_name, new_psk)
        )
        self.assertEqual(
            expected_psks, psk.add_service_psk(current_psks, new_name, new_psk)
        )

    def test_add_service_psk_returns_normalized_sorted_list(self):
        """
        Assert add_service_psk adds the psk in sorted order.

        This test asserts that add_service_psk adds the psk in sorted order
        and returns a normalized list of psks.
        """
        current_psks = "C-serVice:0303CCCC,b-sERVice:0202BBBB"
        new_name = "a,SErvice"
        new_psk = "0101AAAA"
        expected_psks = "a-service:0101AAAA,b-service:0202BBBB,c-service:0303CCCC"
        self.assertEqual(
            expected_psks, psk.add_service_psk(current_psks, new_name, new_psk)
        )
