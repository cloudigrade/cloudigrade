"""Tests for api.util.calculate_max_concurrent_usage_from_runs."""
import datetime

from django.test import TestCase

from api.models import ConcurrentUsage
from api.tests import helper as api_helper
from api.util import (
    calculate_max_concurrent_usage_from_runs,
)
from util.misc import get_today
from util.tests import helper as util_helper


class CalculateMaxConcurrentUsageFromRunsTest(TestCase):
    """Test cases for calculate_max_concurrent_usage_from_runs."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user = util_helper.generate_test_user()
        self.account = api_helper.generate_cloud_account(user=self.user)
        self.account2 = api_helper.generate_cloud_account(user=self.user)
        self.image_rhel_role = "Red Hat Enterprise Linux Workstation"
        self.image_rhel_sla = "Premium"
        self.image_rhel_usage = "Production"
        self.image_service_type = "L3"
        self.image_rhel = api_helper.generate_image(
            rhel_detected=True,
            syspurpose={
                "role": self.image_rhel_role,
                "service_level_agreement": self.image_rhel_sla,
                "usage": self.image_rhel_usage,
                "service_type": self.image_service_type,
            },
        )
        self.image_plain = api_helper.generate_image()

        self.instance_type_small = "t2.nano"  # 1 vcpu, 0.5 GB memory
        self.instance_type_small_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_small
        ]
        self.instance_type_large = "c5.xlarge"  # 4 vcpu, 8.0 GB memory
        self.instance_type_large_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_large
        ]

    def assertConcurrentUsageIs(self, usage, date, user, expected_counts):
        """Assert ConcurrentUsage matches expected values."""
        self.assertEqual(usage.date, date)
        self.assertEqual(usage.user, user)

        sorted_actual_counts = sorted(
            usage.maximum_counts,
            key=lambda d: (
                d["arch"],
                d["role"],
                d["sla"],
                d["usage"],
                d["service_type"],
            ),
        )
        sorted_expected_counts = sorted(
            expected_counts,
            key=lambda d: (
                d["arch"],
                d["role"],
                d["sla"],
                d["usage"],
                d["service_type"],
            ),
        )
        self.assertEqual(len(sorted_actual_counts), len(sorted_expected_counts))
        for actual, expected in zip(sorted_actual_counts, sorted_expected_counts):
            self.assertEqual(actual, expected)

    def generate_all_concurrent_usage_keys(
        self, arch, role, sla, usage, service_type, instance_count=1
    ):
        """Generate the set of all concurrent usage keys for one run."""
        return [
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": "_ANY",
                "usage": "_ANY",
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": "_ANY",
                "usage": "_ANY",
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": "_ANY",
                "usage": usage,
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": "_ANY",
                "usage": usage,
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": sla,
                "usage": "_ANY",
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": sla,
                "usage": "_ANY",
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": sla,
                "usage": usage,
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": "_ANY",
                "sla": sla,
                "usage": usage,
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": "_ANY",
                "usage": "_ANY",
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": "_ANY",
                "usage": "_ANY",
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": "_ANY",
                "usage": usage,
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": "_ANY",
                "usage": usage,
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": sla,
                "usage": "_ANY",
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": sla,
                "usage": "_ANY",
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": sla,
                "usage": usage,
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": arch,
                "role": "_ANY",
                "sla": sla,
                "usage": usage,
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": "_ANY",
                "usage": "_ANY",
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": "_ANY",
                "usage": "_ANY",
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": "_ANY",
                "usage": usage,
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": "_ANY",
                "usage": usage,
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": sla,
                "usage": "_ANY",
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": sla,
                "usage": "_ANY",
                "service_type": service_type,
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": sla,
                "usage": usage,
                "service_type": "_ANY",
                "instances_count": instance_count,
            },
            {
                "arch": "_ANY",
                "role": role,
                "sla": sla,
                "usage": usage,
                "service_type": service_type,
                "instances_count": instance_count,
            },
        ]

    def test_one_clount_one_run_one_day(self):
        """
        Test with one clount having one run in one day.

        This should result in two usages: one is for the user+clount and one is
        for the user+no clount.
        """
        instance = api_helper.generate_instance(self.account, image=self.image_rhel)
        run = api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_small,
            calculate_concurrent_usage=False,
        )
        calculate_max_concurrent_usage_from_runs([run])
        usages = ConcurrentUsage.objects.all()
        self.assertEqual(len(usages), 1)

        expected_counts = self.generate_all_concurrent_usage_keys(
            "x86_64",
            self.image_rhel_role,
            self.image_rhel_sla,
            self.image_rhel_usage,
            self.image_service_type,
        )
        no_cloud_account_usage = ConcurrentUsage.objects.filter().get()
        self.assertConcurrentUsageIs(
            no_cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            expected_counts=expected_counts,
        )

    def test_one_clount_one_run_two_days(self):
        """
        Test with one clount having one run spanning two days.

        This should result in four usages:
        - day 1 user and clount
        - day 1 user and no clount
        - day 2 user and clount
        - day 2 user and no clount
        """
        instance = api_helper.generate_instance(self.account, image=self.image_rhel)
        run = api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_small,
            calculate_concurrent_usage=False,
        )
        calculate_max_concurrent_usage_from_runs([run])
        usages = ConcurrentUsage.objects.all()
        self.assertEqual(len(usages), 2)

        expected_counts = self.generate_all_concurrent_usage_keys(
            "x86_64",
            self.image_rhel_role,
            self.image_rhel_sla,
            self.image_rhel_usage,
            self.image_service_type,
        )

        no_cloud_account_usages = ConcurrentUsage.objects.filter().order_by("date")
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[0],
            date=datetime.date(2019, 5, 1),
            user=self.user,
            expected_counts=expected_counts,
        )
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[1],
            date=datetime.date(2019, 5, 2),
            user=self.user,
            expected_counts=expected_counts,
        )

    def test_one_clount_one_run_with_no_end_two_days(self):
        """
        Test with one clount having one run starting yesterday and no end.

        Since there is no known end date, we can only calculate dates to today.

        This should result in four usages:
        - yesterday user and clount
        - yesterday user and no clount
        - today user and clount
        - today user and no clount
        """
        instance = api_helper.generate_instance(self.account, image=self.image_rhel)
        today = get_today()
        yesterday = today - datetime.timedelta(days=1)
        run = api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(
                    yesterday.year, yesterday.month, yesterday.day, 1, 0, 0
                ),
                None,
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_small,
            calculate_concurrent_usage=False,
        )
        calculate_max_concurrent_usage_from_runs([run])
        usages = ConcurrentUsage.objects.all()
        self.assertEqual(len(usages), 2)

        expected_counts = self.generate_all_concurrent_usage_keys(
            "x86_64",
            self.image_rhel_role,
            self.image_rhel_sla,
            self.image_rhel_usage,
            self.image_service_type,
        )

        no_cloud_account_usages = ConcurrentUsage.objects.filter().order_by("date")
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[0],
            date=yesterday,
            user=self.user,
            expected_counts=expected_counts,
        )
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[1],
            date=today,
            user=self.user,
            expected_counts=expected_counts,
        )

    def test_new_later_dates_ignore_older_dates_data(self):
        """Test calculating from later run dates should ignore older data."""
        instance = api_helper.generate_instance(self.account, image=self.image_rhel)
        old_run = api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_small,
            calculate_concurrent_usage=False,
        )
        # These will act as the "old" calculated concurrent objects.
        calculate_max_concurrent_usage_from_runs([old_run])
        old_usages = ConcurrentUsage.objects.all().order_by("created_at", "id")
        self.assertEqual(len(old_usages), 1)

        new_run = api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(2019, 5, 2, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 2, 2, 0, 0),
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_large,
            calculate_concurrent_usage=False,
        )
        # This should have no effect on the old calculated concurrent objects.
        calculate_max_concurrent_usage_from_runs([new_run])
        new_usages = ConcurrentUsage.objects.all().order_by("created_at", "id")
        self.assertEqual(len(new_usages), 2)
        self.assertEqual(new_usages[0], old_usages[0])

    def test_same_date_new_run_causes_deletion_and_recreation(self):
        """
        Test calculation from a run on the same day deletes and recalculates.

        In this case, the new run also overlaps the old run, and that means the
        new calculated results should also have greater numbers than the old.
        """
        instance = api_helper.generate_instance(self.account, image=self.image_rhel)
        old_run = api_helper.generate_single_run(
            instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_small,
            calculate_concurrent_usage=False,
        )
        # These will act as the "old" calculated concurrent objects.
        calculate_max_concurrent_usage_from_runs([old_run])
        old_usages = ConcurrentUsage.objects.all().order_by("created_at", "id")
        self.assertEqual(len(old_usages), 1)

        new_instance = api_helper.generate_instance(self.account, image=self.image_rhel)
        new_run = api_helper.generate_single_run(
            new_instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                util_helper.utc_dt(2019, 5, 1, 2, 30, 0),
            ),
            image=instance.machine_image,
            instance_type=self.instance_type_large,
            calculate_concurrent_usage=False,
        )
        # This should create new and different runs.
        calculate_max_concurrent_usage_from_runs([new_run])
        new_usages = ConcurrentUsage.objects.all().order_by("created_at", "id")
        self.assertEqual(len(new_usages), 1)
        self.assertNotEqual(new_usages[0].id, old_usages[0].id)

        expected_counts = self.generate_all_concurrent_usage_keys(
            "x86_64",
            self.image_rhel_role,
            self.image_rhel_sla,
            self.image_rhel_usage,
            self.image_service_type,
            instance_count=2,
        )

        no_cloud_account_usage = ConcurrentUsage.objects.filter().get()
        self.assertConcurrentUsageIs(
            no_cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            expected_counts=expected_counts,
        )
