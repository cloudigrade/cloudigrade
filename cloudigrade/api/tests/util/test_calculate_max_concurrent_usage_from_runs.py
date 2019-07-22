"""Tests for api.util.calculate_max_concurrent_usage_from_runs."""
import datetime

from django.test import TestCase

from api.models import ConcurrentUsage
from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage_from_runs
from util.misc import get_today
from util.tests import helper as util_helper


class CalculateMaxConcurrentUsageFromRunsTest(TestCase):
    """Test cases for calculate_max_concurrent_usage_from_runs."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user = util_helper.generate_test_user()
        self.account = api_helper.generate_aws_account(user=self.user)
        self.account2 = api_helper.generate_aws_account(user=self.user)
        self.image_rhel = api_helper.generate_aws_image(rhel_detected=True)
        self.image_plain = api_helper.generate_aws_image()

        self.instance_type_small = 't2.nano'  # 1 vcpu, 0.5 GB memory
        self.instance_type_small_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_small
        ]
        self.instance_type_large = 'c5.xlarge'  # 4 vcpu, 8.0 GB memory
        self.instance_type_large_specs = util_helper.SOME_EC2_INSTANCE_TYPES[
            self.instance_type_large
        ]

    def assertConcurrentUsageIs(
        self, usage, date, user, cloud_account, instances, memory, vcpu
    ):
        """Assert ConcurrentUsage matches expected values."""
        self.assertEqual(usage.date, date)
        self.assertEqual(usage.user, user)
        if cloud_account is None:
            self.assertIsNone(usage.cloud_account)
        else:
            self.assertEqual(usage.cloud_account, cloud_account)
        self.assertEqual(usage.instances, instances)
        self.assertEqual(usage.memory, memory)
        self.assertEqual(usage.vcpu, vcpu)

    def test_one_clount_one_run_one_day(self):
        """
        Test with one clount having one run in one day.

        This should result in two usages: one is for the user+clount and one is
        for the user+no clount.
        """
        instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
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
        self.assertEqual(len(usages), 2)

        cloud_account_usage = ConcurrentUsage.objects.filter(
            cloud_account__isnull=False
        ).get()
        self.assertConcurrentUsageIs(
            cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=self.account,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )

        no_cloud_account_usage = ConcurrentUsage.objects.filter(
            cloud_account__isnull=True
        ).get()
        self.assertConcurrentUsageIs(
            no_cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=None,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )

    def test_two_clounts_each_one_run_one_day(self):
        """
        Test with two same-user clounts each having one run in the same day.

        This should result in three usages:
        - user and clount 1 (small instance)
        - user and clount 2 (large instance)
        - user and no clount (both instances)
        """
        runs = []
        instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
        runs.append(
            api_helper.generate_single_run(
                instance,
                (
                    util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                    util_helper.utc_dt(2019, 5, 1, 2, 0, 0),
                ),
                image=instance.machine_image,
                instance_type=self.instance_type_small,
                calculate_concurrent_usage=False,
            )
        )
        instance2 = api_helper.generate_aws_instance(
            self.account2, image=self.image_rhel
        )
        runs.append(
            api_helper.generate_single_run(
                instance2,
                (
                    util_helper.utc_dt(2019, 5, 1, 1, 30, 0),
                    util_helper.utc_dt(2019, 5, 1, 2, 30, 0),
                ),
                image=instance2.machine_image,
                instance_type=self.instance_type_large,
                calculate_concurrent_usage=False,
            )
        )
        calculate_max_concurrent_usage_from_runs(runs)
        usages = ConcurrentUsage.objects.all()
        self.assertEqual(len(usages), 3)

        no_cloud_account_usage = ConcurrentUsage.objects.filter(
            cloud_account__isnull=True
        ).get()
        self.assertConcurrentUsageIs(
            no_cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=None,
            instances=2,
            memory=(
                self.instance_type_small_specs['memory'] +
                self.instance_type_large_specs['memory']
            ),
            vcpu=(
                self.instance_type_small_specs['vcpu'] +
                self.instance_type_large_specs['vcpu']
            ),
        )

        cloud_account_usage = ConcurrentUsage.objects.filter(
            cloud_account=self.account
        ).get()
        self.assertConcurrentUsageIs(
            cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=self.account,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )

        cloud_account2_usage = ConcurrentUsage.objects.filter(
            cloud_account=self.account2
        ).get()
        self.assertConcurrentUsageIs(
            cloud_account2_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=self.account2,
            instances=1,
            memory=self.instance_type_large_specs['memory'],
            vcpu=self.instance_type_large_specs['vcpu'],
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
        instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
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
        self.assertEqual(len(usages), 4)

        cloud_account_usages = ConcurrentUsage.objects.filter(
            cloud_account__isnull=False
        ).order_by('date')
        self.assertConcurrentUsageIs(
            cloud_account_usages[0],
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=self.account,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )
        self.assertConcurrentUsageIs(
            cloud_account_usages[1],
            date=datetime.date(2019, 5, 2),
            user=self.user,
            cloud_account=self.account,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )

        no_cloud_account_usages = ConcurrentUsage.objects.filter(
            cloud_account__isnull=True
        ).order_by('date')
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[0],
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=None,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[1],
            date=datetime.date(2019, 5, 2),
            user=self.user,
            cloud_account=None,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
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
        instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
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
        self.assertEqual(len(usages), 4)

        cloud_account_usages = ConcurrentUsage.objects.filter(
            cloud_account__isnull=False
        ).order_by('date')
        self.assertConcurrentUsageIs(
            cloud_account_usages[0],
            date=yesterday,
            user=self.user,
            cloud_account=self.account,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )
        self.assertConcurrentUsageIs(
            cloud_account_usages[1],
            date=today,
            user=self.user,
            cloud_account=self.account,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )

        no_cloud_account_usages = ConcurrentUsage.objects.filter(
            cloud_account__isnull=True
        ).order_by('date')
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[0],
            date=yesterday,
            user=self.user,
            cloud_account=None,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )
        self.assertConcurrentUsageIs(
            no_cloud_account_usages[1],
            date=today,
            user=self.user,
            cloud_account=None,
            instances=1,
            memory=self.instance_type_small_specs['memory'],
            vcpu=self.instance_type_small_specs['vcpu'],
        )

    def test_new_later_dates_ignore_older_dates_data(self):
        """Test calculating from later run dates should ignore older data."""
        instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
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
        old_usages = ConcurrentUsage.objects.all().order_by('created_at', 'id')
        self.assertEqual(len(old_usages), 2)

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
        new_usages = ConcurrentUsage.objects.all().order_by('created_at', 'id')
        self.assertEqual(len(new_usages), 4)
        self.assertEqual(new_usages[:2], old_usages[:2])

    def test_same_date_new_run_causes_deletion_and_recreation(self):
        """
        Test calculation from a run on the same day deletes and recalculates.

        In this case, the new run also overlaps the old run, and that means the
        new calculated results should also have greater numbers than the old.
        """
        instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
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
        old_usages = ConcurrentUsage.objects.all().order_by('created_at', 'id')
        self.assertEqual(len(old_usages), 2)

        new_instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
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
        new_usages = ConcurrentUsage.objects.all().order_by('created_at', 'id')
        self.assertEqual(len(new_usages), 2)
        self.assertNotEqual(new_usages[0].id, old_usages[0].id)
        self.assertNotEqual(new_usages[1].id, old_usages[1].id)

        cloud_account_usage = ConcurrentUsage.objects.filter(
            cloud_account__isnull=False
        ).get()
        self.assertConcurrentUsageIs(
            cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=self.account,
            instances=2,
            memory=(
                self.instance_type_small_specs['memory'] +
                self.instance_type_large_specs['memory']
            ),
            vcpu=(
                self.instance_type_small_specs['vcpu'] +
                self.instance_type_large_specs['vcpu']
            ),
        )

        no_cloud_account_usage = ConcurrentUsage.objects.filter(
            cloud_account__isnull=True
        ).get()
        self.assertConcurrentUsageIs(
            no_cloud_account_usage,
            date=datetime.date(2019, 5, 1),
            user=self.user,
            cloud_account=None,
            instances=2,
            memory=(
                self.instance_type_small_specs['memory'] +
                self.instance_type_large_specs['memory']
            ),
            vcpu=(
                self.instance_type_small_specs['vcpu'] +
                self.instance_type_large_specs['vcpu']
            ),
        )
