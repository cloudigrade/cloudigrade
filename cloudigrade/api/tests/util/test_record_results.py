"""Collection of tests for api.util._record_results."""
import collections
import datetime

from django.test import TestCase

from api.tests import helper as api_helper
from api.util import ANY, _record_results
from util.tests import helper as util_helper

ConcurrentKey = collections.namedtuple("ConcurrentKey", ["role", "sla", "arch"])


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
        }
        self.syspurpose2 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "Premium",
            "usage": "Development/Test",
        }
        self.syspurpose3 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "",
            "usage": "Development/Test",
        }
        self.syspurpose4 = {
            "role": "Red Hat Enterprise Linux Server Workstation",
            "service_level_agreement": "," * 10485760,  # 10 mb of commas
            "usage": "Development/Test",
        }
        self.syspurpose5 = {
            "role": "The quick brown fox jumps over the lazy dog. " * 3,
            "service_level_agreement": "Self-Support",
            "usage": "Development/Test",
        }
        self.syspurpose6 = {
            "role": "",
            "service_level_agreement": "",
            "usage": "",
        }
        self.syspurpose7 = {
            "role": "Red Hat Enterprise Linux Server",
            "service_level_agreement": "",
            "usage": "Development/Test",
        }

    def test_records_all(self):
        """Record everything."""
        test_items = [
            (True, self.syspurpose1, self.x86_64,),
            (True, self.syspurpose2, self.arm64,),
            (True, self.syspurpose3, self.x86_64,),
            (True, self.syspurpose4, self.arm64,),
            (True, self.syspurpose5, self.x86_64,),
            (True, self.syspurpose6, self.arm64,),
            (True, self.syspurpose6, self.x86_64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        self.assertEqual(len(results), 17)

    def test_one_for_each_sla(self):
        """Record one for each SLA."""
        test_items = [
            (True, self.syspurpose1, self.x86_64,),
            (True, self.syspurpose2, self.x86_64,),
            (True, self.syspurpose3, self.x86_64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        self.assertEqual(len(results), 10)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose1["service_level_agreement"], arch=ANY
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose2["service_level_agreement"], arch=ANY
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose3["service_level_agreement"], arch=ANY
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_unknown_sla(self):
        """Record for unknown SLA."""
        test_items = [
            (True, self.syspurpose7, self.x86_64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        # self.assertEqual(self.results["date"], self.date)
        self.assertEqual(len(results), 4)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose7["service_level_agreement"], arch=ANY
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_one_for_each_sla_role(self):
        """Record for each role and sla combination."""
        test_items = [
            (True, self.syspurpose1, self.x86_64,),
            (True, self.syspurpose2, self.x86_64,),
            (True, self.syspurpose4, self.x86_64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        self.assertEqual(len(results), 10)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=self.syspurpose1["role"],
            sla=self.syspurpose1["service_level_agreement"],
            arch=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=self.syspurpose2["role"],
            sla=self.syspurpose2["service_level_agreement"],
            arch=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=self.syspurpose4["role"],
            sla=self.syspurpose4["service_level_agreement"][:64],
            arch=ANY,
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_one_for_each_role_no_sla(self):
        """Record for each role and unknown sla combination."""
        test_items = [
            (True, self.syspurpose3, self.x86_64,),
            (True, self.syspurpose7, self.x86_64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        self.assertEqual(len(results), 4)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=self.syspurpose3["role"],
            sla=self.syspurpose3["service_level_agreement"],
            arch=ANY,
        )
        self.assertEqual(results[key]["max_count"], 2)
        key = ConcurrentKey(
            role=self.syspurpose7["role"],
            sla=self.syspurpose7["service_level_agreement"],
            arch=ANY,
        )
        self.assertEqual(results[key]["max_count"], 2)

    def test_one_for_each_arch_sla(self):
        """Record one for each arch and sla combination."""
        test_items = [
            (True, self.syspurpose1, self.x86_64,),
            (True, self.syspurpose1, self.arm64,),
            (True, self.syspurpose2, self.arm64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        self.assertEqual(len(results), 8)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose1["service_level_agreement"], arch=self.x86_64
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose1["service_level_agreement"], arch=self.arm64
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose2["service_level_agreement"], arch=self.arm64
        )
        self.assertEqual(results[key]["max_count"], 1)

    def test_one_for_each_arch_no_sla(self):
        """Record for each arch and no sla combination."""
        test_items = [
            (True, self.syspurpose3, self.x86_64,),
            (True, self.syspurpose6, self.arm64,),
            (True, self.syspurpose7, self.arm64,),
        ]

        results = {}
        for (is_start, syspurpose, arch) in test_items:
            _record_results(results, is_start, syspurpose, arch)

        self.assertEqual(len(results), 5)
        key = ConcurrentKey(role=ANY, sla=ANY, arch=ANY)
        self.assertEqual(results[key]["max_count"], len(test_items))

        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose3["service_level_agreement"], arch=self.x86_64
        )
        self.assertEqual(results[key]["max_count"], 1)
        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose6["service_level_agreement"], arch=self.arm64
        )
        self.assertEqual(results[key]["max_count"], 2)
        key = ConcurrentKey(
            role=ANY, sla=self.syspurpose7["service_level_agreement"], arch=self.arm64
        )
        self.assertEqual(results[key]["max_count"], 2)
