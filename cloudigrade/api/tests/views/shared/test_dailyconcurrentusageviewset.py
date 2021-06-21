"""Collection of shared tests for ConcurrentUsageView."""
import datetime
from unittest.mock import patch

import faker
from django.test import TransactionTestCase
from django.utils.translation import gettext as _
from rest_framework.test import APIClient, APIRequestFactory

from api.models import ConcurrentUsageCalculationTask
from api.tests import helper as api_helper
from util.misc import get_today
from util.tests import helper as util_helper


class SharedDailyConcurrentUsageViewSetTest(TransactionTestCase):
    """SharedCommonDailyConcurrentUsageViewSet test case."""

    def setUp(self, concurrent_api_url="/api/cloudigrade/v2/concurrent/"):
        """Set up a bunch of test data."""
        self.concurrent_api_url = concurrent_api_url
        self.user1 = util_helper.generate_test_user()
        self.user1.date_joined = util_helper.utc_dt(2019, 1, 1, 0, 0, 0)
        self.user1.save()
        self.account1 = api_helper.generate_cloud_account(user=self.user1)
        self.account2 = api_helper.generate_cloud_account(user=self.user1)
        self.image1_rhel = api_helper.generate_image(
            rhel_detected=True,
            rhel_version="7.7",
            syspurpose={"role": "potato"},
        )
        self.image2_rhel = api_helper.generate_image(rhel_detected=True)
        self.instance1 = api_helper.generate_instance(
            self.account1, image=self.image1_rhel
        )
        self.instance2 = api_helper.generate_instance(
            self.account1, image=self.image2_rhel
        )
        self.instance_type1 = "c5.xlarge"  # 4 vcpu and 8.0 memory
        self.factory = APIRequestFactory()
        self.faker = faker.Faker()

    @util_helper.clouditardis(util_helper.utc_dt(2019, 4, 17, 0, 0, 0))
    def test_daily_pagination(self):
        """
        Test proper pagination handling of days from the custom queryset.

        This test asserts that the pagination envelope is correctly populated
        and that the included list is populated with the expected dates with
        calculated concurrency values.

        We ask for 31 days worth of concurrency here, but default pagination
        should limit the response to the first 10 days.

        One instance run exist in the first day of this period. All other days
        have no activity. Therefore, only that first day should have non-zero
        values for instances; all other days should have 0s.
        """
        api_helper.generate_single_run(
            self.instance1,
            (
                util_helper.utc_dt(2019, 3, 15, 1, 0, 0),
                util_helper.utc_dt(2019, 3, 15, 2, 0, 0),
            ),
            image=self.instance1.machine_image,
            instance_type=self.instance_type1,
        )
        api_helper.generate_single_run(
            self.instance1,
            (
                util_helper.utc_dt(2019, 3, 16, 1, 0, 0),
                util_helper.utc_dt(2019, 3, 16, 2, 0, 0),
            ),
            image=self.instance1.machine_image,
            instance_type=self.instance_type1,
        )
        api_helper.generate_single_run(
            self.instance2,
            (
                util_helper.utc_dt(2019, 3, 16, 1, 0, 0),
                util_helper.utc_dt(2019, 3, 17, 2, 0, 0),
            ),
            image=self.instance2.machine_image,
            instance_type=self.instance_type1,
        )

        start_date = datetime.date(2019, 3, 15)
        end_date = datetime.date(2019, 4, 15)

        api_helper.calculate_concurrent(start_date, end_date, self.user1.id)
        data = {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        body = response.json()

        self.assertEquals(body["meta"]["count"], 31)
        self.assertEquals(len(body["data"]), 10)

        link_first = body["links"]["first"]
        self.assertIn("offset=0", link_first)
        self.assertIn("start_date=2019-03-15", link_first)
        self.assertIn("end_date=2019-04-15", link_first)

        link_next = body["links"]["next"]
        self.assertIn("offset=10", link_next)
        self.assertIn("start_date=2019-03-15", link_next)
        self.assertIn("end_date=2019-04-15", link_next)

        self.assertIsNone(body["links"]["previous"])

        link_last = body["links"]["last"]
        self.assertIn("offset=21", link_last)
        self.assertIn("start_date=2019-03-15", link_last)
        self.assertIn("end_date=2019-04-15", link_last)

        first_date = datetime.date(2019, 3, 15)
        first_result = body["data"][0]

        self.assertEqual(first_result["maximum_counts"][0]["instances_count"], 1)
        self.assertEqual(first_result["date"], str(first_date))

        second_date = datetime.date(2019, 3, 16)
        second_result = body["data"][1]

        self.assertEqual(second_result["maximum_counts"][0]["instances_count"], 2)
        self.assertEqual(second_result["date"], str(second_date))

        third_date = datetime.date(2019, 3, 17)
        third_result = body["data"][2]

        self.assertEqual(third_result["maximum_counts"][0]["instances_count"], 1)
        self.assertEqual(third_result["date"], str(third_date))

        # assert that every other day exists with zero reported concurrency.
        for offset, result in enumerate(body["data"][3:]):
            this_date = third_date + datetime.timedelta(days=offset + 1)
            self.assertEqual(result["maximum_counts"], [])
            self.assertEqual(result["date"], str(this_date))

    def test_bad_start_date_and_end_date_arguments(self):
        """Test with bad date arguments."""
        data = {"start_date": "potato", "end_date": "gems"}
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(
            body["start_date"], [_("start_date must be a date (YYYY-MM-DD).")]
        )
        self.assertEqual(body["end_date"], [_("end_date must be a date (YYYY-MM-DD).")])

    def test_start_date_is_inclusive_and_end_date_is_exclusive(self):
        """Test that start_date is inclusive and end_date is exclusive."""
        start_date = datetime.date(2019, 1, 1)
        end_date = datetime.date(2019, 1, 4)
        data = {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }
        api_helper.calculate_concurrent(start_date, end_date, self.user1.id)

        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        body = response.json()
        self.assertEqual(body["meta"]["count"], 3)
        self.assertEqual(len(body["data"]), 3)
        self.assertEqual(body["data"][0]["date"], "2019-01-01")
        self.assertEqual(body["data"][1]["date"], "2019-01-02")
        self.assertEqual(body["data"][2]["date"], "2019-01-03")

    def test_start_date_end_date_defaults(self):
        """
        Test with no start_date and no end_date set.

        Default start_date is "yesterday" and default end_date is "today", and
        since start_date is inclusive and end_date is exclusive, the resulting
        output should be data for one day: yesterday.
        """
        yesterday = get_today() - datetime.timedelta(days=1)
        today = get_today()
        data = {}
        api_helper.calculate_concurrent(yesterday, today, self.user1.id)

        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        body = response.json()
        self.assertEqual(body["meta"]["count"], 1)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["date"], str(yesterday))

    def test_future_end_date_returns_400(self):
        """
        Test with far-future end_date, expecting it to return 400.

        When an end_date is given that is later than today, we return
        a 400 response, because we cannot predict the future.
        """
        yesterday = get_today() - datetime.timedelta(days=1)
        future = yesterday + datetime.timedelta(days=100)
        data = {"end_date": str(future)}
        api_helper.calculate_concurrent(yesterday, future, self.user1.id)

        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        self.assertEqual(response.status_code, 400)

        body = response.json()
        self.assertEqual(body["end_date"], [_("end_date cannot be in the future.")])

    def test_end_date_before_user_create_date_returns_400(self):
        """
        Test with end_date preceding the user creation date, expecting no results.

        When we give an end_date that is before the user creation date, we return
        a 400 because we do not know anything before the user creation date.
        """
        past_start = datetime.date(2018, 12, 1)
        past_end = datetime.date(2018, 12, 31)
        data = {"start_date": str(past_start), "end_date": str(past_end)}
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")
        self.assertEqual(response.status_code, 400)

        body = response.json()
        self.assertEqual(
            body["end_date"],
            [_("end_date must be same as or after the user creation date.")],
        )

    @patch("api.tasks.calculate_max_concurrent_usage_task")
    def test_end_date_same_as_user_create_date_expect_425(self, mock_calculate_task):
        """
        Test with end_date exactly as the user creation date, expecting 425.

        When we give an end_date that is the same as the user creation date,
        and no concurrent data, we expect a 425.
        """
        end_date = self.user1.date_joined.date()
        start_date = end_date - datetime.timedelta(days=1)
        data = {"start_date": str(start_date), "end_date": str(end_date)}
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get(self.concurrent_api_url, data=data, format="json")

        self.assertEqual(1, ConcurrentUsageCalculationTask.objects.count())
        self.assertEqual(response.status_code, 425)

    @patch("api.tasks.calculate_max_concurrent_usage_task")
    def test_425_if_no_concurrent_usage(self, mock_calculate_task):
        """Test if no concurrent usage is present, an 425 error code is returned."""
        start_date = datetime.date(2019, 1, 1)
        end_date = datetime.date(2019, 1, 4)
        data = {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }

        client = APIClient()
        client.force_authenticate(user=self.user1)
        self.assertEqual(0, ConcurrentUsageCalculationTask.objects.count())

        response = client.get(self.concurrent_api_url, data=data, format="json")
        self.assertEqual(3, ConcurrentUsageCalculationTask.objects.count())
        self.assertEqual(response.status_code, 425)
