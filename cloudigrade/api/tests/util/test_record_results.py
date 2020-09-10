"""Collection of tests for api.util._record_results."""
import datetime

from django.test import TestCase

from api.tests import helper as api_helper
from api.util import ANY, ConcurrentKey, _record_results
from util.tests import helper as util_helper


class CalculateMaxConcurrentUsageTest(TestCase):
    """Test cases for api.util.calculate_max_concurrent_usage."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user1account1 = api_helper.generate_cloud_account(user=self.user1)
        self.date = datetime.date(2019, 5, 1)

        self.x86_64 = "x86_64"
        self.arm64 = "arm64"

        self.syspurpose1 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "Standard",
            "usage": "Development/Test",
            "service_type": "PSF",
        }
        self.syspurpose2 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "Premium",
            "usage": "Development/Test",
            "service_type": "L3",
        }
        self.syspurpose3 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "",
            "usage": "Development/Test",
            "service_type": "PSF",
        }
        self.syspurpose4 = {
            "role": "Red Hat Enterprise Linux Server Workstation",
            "service_level_agreement": "," * 10485760,  # 10 mb of commas
            "usage": "Development/Test",
            "service_type": "",
        }
        self.syspurpose5 = {
            "role": "The quick brown fox jumps over the lazy dog. " * 3,
            "service_level_agreement": "Self-Support",
            "usage": "Development/Test",
            "service_type": "",
        }
        self.syspurpose6 = {
            "role": "",
            "service_level_agreement": "",
            "usage": "",
            "service_type": "",
        }
        self.syspurpose7 = {
            "role": "",
            "service_level_agreement": "Standard",
            "usage": "Development/Test",
            "service_type": "L3",
        }
        self.syspurpose8 = {
            "role": "Red Hat Enterprise Linux Server Workstation",
            "service_level_agreement": "",
            "usage": "Production",
            "service_type": "L3",
        }
        self.syspurpose9 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "Standard",
            "usage": "",
            "service_type": "L3",
        }
        self.syspurpose10 = {
            "role": "",
            "service_level_agreement": "",
            "usage": "",
            "service_type": "L3",
        }

    def test_single_record(self):
        """Test a single record."""
        results = _record_results({}, True, self.syspurpose1, self.x86_64)
        self.assertEqual(len(results), 24)

    def test_single_empty_record(self):
        """Test a single empty record."""
        results = _record_results({}, True, self.syspurpose6, self.x86_64)
        self.assertEqual(len(results), 24)

    def test_one_empty_one_mostly_record(self):
        """Test two almost empty records."""
        test_items = [
            (
                True,
                self.syspurpose6,
                "",
            ),
            (
                True,
                self.syspurpose10,
                "",
            ),
        ]
        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], 2)

        key = ConcurrentKey(role="", sla="", arch=ANY, usage="", service_type=ANY)
        self.assertEqual(results[key]["max_count"], 2)

        key = ConcurrentKey(role=ANY, sla="", arch="", usage="", service_type=ANY)
        self.assertEqual(results[key]["max_count"], 2)

        key = ConcurrentKey(role=ANY, sla="", arch="", usage="", service_type="")
        self.assertEqual(results[key]["max_count"], 1)
        self.assertEqual(len(results), 36)

    def test_records_all(self):
        """Record everything."""
        test_items = [
            (
                True,
                self.syspurpose1,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose2,
                self.arm64,
            ),
            (
                True,
                self.syspurpose3,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose4,
                self.arm64,
            ),
            (
                True,
                self.syspurpose5,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose6,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose7,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose8,
                self.arm64,
            ),
            (
                True,
                self.syspurpose9,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose10,
                self.arm64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))
        key = ConcurrentKey(
            role=ANY, sla=ANY, arch=self.x86_64, usage=ANY, service_type=ANY
        )
        self.assertEqual(results[key]["max_count"], 6)
        key = ConcurrentKey(
            role="Red Hat Enterprise Linux Server",
            sla=ANY,
            arch=ANY,
            usage="Development/Test",
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 3)

    def test_one_for_each_sla(self):
        """Record one for each SLA."""
        test_items = [
            (
                True,
                self.syspurpose1,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose2,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose3,
                self.x86_64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose1["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose2["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose3["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_unknown_sla(self):
        """Record for unknown SLA."""
        test_items = [
            (
                True,
                self.syspurpose7,
                self.x86_64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose7["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_one_for_each_sla_role(self):
        """Record for each role and sla combination."""
        test_items = [
            (
                True,
                self.syspurpose1,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose2,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose4,
                self.x86_64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=self.syspurpose1["role"],
            sla=self.syspurpose1["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=self.syspurpose2["role"],
            sla=self.syspurpose2["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=self.syspurpose4["role"],
            sla=self.syspurpose4["service_level_agreement"][:64],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_one_for_each_role_no_sla(self):
        """Record for each role and unknown sla combination."""
        test_items = [
            (
                True,
                self.syspurpose3,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose8,
                self.x86_64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=self.syspurpose3["role"],
            sla=ANY,
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose8["service_level_agreement"],
            arch=ANY,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 2)

    def test_one_for_each_arch_sla(self):
        """Record one for each arch and sla combination."""
        test_items = [
            (
                True,
                self.syspurpose1,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose1,
                self.arm64,
            ),
            (
                True,
                self.syspurpose2,
                self.arm64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose1["service_level_agreement"],
            arch=self.x86_64,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose1["service_level_agreement"],
            arch=self.arm64,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose2["service_level_agreement"],
            arch=self.arm64,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_one_for_each_arch_no_sla(self):
        """Record for each arch and no sla combination."""
        test_items = [
            (
                True,
                self.syspurpose3,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose6,
                self.arm64,
            ),
            (
                True,
                self.syspurpose7,
                self.arm64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose3["service_level_agreement"],
            arch=self.x86_64,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose6["service_level_agreement"],
            arch=self.arm64,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY,
            sla=self.syspurpose7["service_level_agreement"],
            arch=self.arm64,
            usage=ANY,
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_unknown_usage(self):
        """Record for unknown role."""
        test_items = [
            (
                True,
                self.syspurpose9,
                self.x86_64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY,
            sla=ANY,
            arch=ANY,
            usage="",
            service_type=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_unknown_service_type(self):
        """Record for unknown role."""
        test_items = [
            (
                True,
                self.syspurpose5,
                self.x86_64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY,
            sla=ANY,
            arch=ANY,
            usage=ANY,
            service_type="",
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_two_different_sysconfig(self):
        """Record for two sysconfigs that share no similarities."""
        test_items = [
            (
                True,
                self.syspurpose1,
                self.x86_64,
            ),
            (
                True,
                self.syspurpose8,
                self.arm64,
            ),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        # Total length of results should be 24+24-1 since the two should only
        # have one ConcurrentKey in common
        self.assertEqual(len(results), 47)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY, usage=ANY, service_type=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))
