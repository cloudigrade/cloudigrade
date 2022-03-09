"""Collection of tests for custom DRF serializers in the internal API."""
import datetime

import faker
from django.test import TransactionTestCase
from rest_framework.test import APIRequestFactory

from api.tests import helper as api_helper
from api.util import calculate_max_concurrent_usage
from internal import viewsets
from util.tests import helper as util_helper

_faker = faker.Faker()


class InternalConcurrentUsageSerializerTest(TransactionTestCase):
    """
    Internal ConcurrentUsage serializer test case.

    Rather than test the serializer directly, for convenience this actually tests
    the behavior of the viewset which calls the serializer, and since we're calling
    the viewset directly instead of going through the router, the url path in each
    generated request doesn't really matter.
    """

    def setUp(self):
        """Set up a bunch of test data."""
        created_at = util_helper.utc_dt(2019, 4, 1, 1, 0, 0)
        with util_helper.clouditardis(created_at):
            self.user = util_helper.generate_test_user()
            self.account = api_helper.generate_cloud_account(user=self.user)
        self.image = api_helper.generate_image(rhel_detected=True)
        self.instance = api_helper.generate_instance(self.account, image=self.image)

        api_helper.generate_single_run(
            self.instance,
            (
                util_helper.utc_dt(2019, 5, 1, 1, 0, 0),
                util_helper.utc_dt(2019, 5, 3, 1, 0, 0),
            ),
            image=self.instance.machine_image,
            calculate_concurrent_usage=False,
        )
        self.request_date = datetime.date(2019, 5, 2)
        calculate_max_concurrent_usage(self.request_date, self.user.id)

        self.factory = APIRequestFactory()

    def test_without_include_runs(self):
        """Assert potentially_related_runs is not included by default."""
        request = self.factory.get("/dummy/path")
        view = viewsets.InternalConcurrentUsageViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertNotIn("potentially_related_runs", response.data["data"][0])

    def test_with_include_runs(self):
        """Assert potentially_related_runs is included when include_runs is set."""
        request = self.factory.get("/dummy/path?include_runs=True")
        view = viewsets.InternalConcurrentUsageViewSet.as_view({"get": "list"})
        response = view(request)
        self.assertIn("potentially_related_runs", response.data["data"][0])
