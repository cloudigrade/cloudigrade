"""Collection of tests for AccountViewSet."""
import datetime

import faker
from django.test import TransactionTestCase
from rest_framework.test import (APIClient, APIRequestFactory)

from api.tests import helper as api_helper
from util.tests import helper as util_helper


class DailyConcurrentUsageViewSetTest(TransactionTestCase):
    """DailyConcurrentUsageViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)
        self.account1 = api_helper.generate_aws_account(user=self.user1)
        self.account2 = api_helper.generate_aws_account(user=self.user1)
        self.image1_rhel = api_helper.generate_aws_image(rhel_detected=True)
        self.instance1 = api_helper.generate_aws_instance(
            self.account1, image=self.image1_rhel
        )
        self.instance_type1 = 'c5.xlarge'  # 4 vcpu and 8.0 memory
        self.factory = APIRequestFactory()
        self.faker = faker.Faker()

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
        values for instances, vcpu, and memory; all other days should have 0s.
        """
        api_helper.generate_single_run(
            self.instance1,
            (
                util_helper.utc_dt(2019, 5, 15, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 15, 2, 0, 0)
            ),
            image=self.instance1.machine_image,
            instance_type=self.instance_type1,
        )

        data = {'start_date': '2019-05-15', 'end_date': '2019-06-15'}
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get('/v2/concurrent/', data=data, format='json')
        body = response.json()

        self.assertEquals(body['meta']['count'], 31)
        self.assertEquals(len(body['data']), 10)

        link_first = body['links']['first']
        self.assertIn('offset=0', link_first)
        self.assertIn('start_date=2019-05-15', link_first)
        self.assertIn('end_date=2019-06-15', link_first)

        link_next = body['links']['next']
        self.assertIn('offset=10', link_next)
        self.assertIn('start_date=2019-05-15', link_next)
        self.assertIn('end_date=2019-06-15', link_next)

        self.assertIsNone(body['links']['previous'])

        link_last = body['links']['last']
        self.assertIn('offset=21', link_last)
        self.assertIn('start_date=2019-05-15', link_last)
        self.assertIn('end_date=2019-06-15', link_last)

        first_date = datetime.date(2019, 5, 15)
        first_result = body['data'][0]

        self.assertEqual(first_result['instances'], 1)
        self.assertEqual(first_result['vcpu'], 4)
        self.assertEqual(first_result['memory'], 8.0)
        self.assertEqual(first_result['date'], str(first_date))

        # assert that every other day exists with zero reported concurrency.
        for offset, result in enumerate(body['data'][1:]):
            this_date = first_date + datetime.timedelta(days=offset + 1)
            self.assertEqual(result['instances'], 0)
            self.assertEqual(result['vcpu'], 0)
            self.assertEqual(result['memory'], 0.0)
            self.assertEqual(result['date'], str(this_date))
