"""Collection of tests for v2 InstanceViewSet."""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.clouds.aws.models import AwsInstance
from api.tests import helper as api_helper
from api.views import InstanceViewSet
from util.tests import helper as util_helper


class InstanceViewSetTest(TestCase):
    """InstanceViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()

        self.account1 = api_helper.generate_cloud_account(user=self.user1)
        self.account2 = api_helper.generate_cloud_account(user=self.user1)
        self.account3 = api_helper.generate_cloud_account(user=self.user2)
        self.account4 = api_helper.generate_cloud_account(user=self.user2)

        self.image_plain = api_helper.generate_image()
        self.image_windows = api_helper.generate_image(is_windows=True)
        self.image_rhel = api_helper.generate_image(rhel_detected=True)
        self.image_ocp = api_helper.generate_image(openshift_detected=True)

        self.instance1 = api_helper.generate_instance(
            cloud_account=self.account1, image=self.image_plain
        )
        self.instance2 = api_helper.generate_instance(
            cloud_account=self.account2, image=self.image_windows
        )
        self.instance3 = api_helper.generate_instance(
            cloud_account=self.account3, image=self.image_rhel
        )
        self.instance4 = api_helper.generate_instance(
            cloud_account=self.account4, image=self.image_ocp
        )
        self.factory = APIRequestFactory()

    def assertResponseHasInstanceData(self, response, instance):
        """Assert the response has data matching the instance object."""
        self.assertEqual(response.data["instance_id"], instance.id)
        self.assertEqual(response.data["cloud_account_id"], instance.cloud_account.id)
        self.assertEqual(response.data["machine_image_id"], instance.machine_image.id)

        if isinstance(instance, AwsInstance):
            self.assertEqual(
                response.data["content_object"]["ec2_instance_id"],
                instance.ec2_instance_id,
            )

    def get_instance_get_response(self, user, instance_id):
        """
        Generate a response for a get-retrieve on the InstanceViewSet.

        Args:
            user (User): Django auth user performing the request
            instance_id (int): the id of the instance to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get("/instances/")
        force_authenticate(request, user=user)
        view = InstanceViewSet.as_view(actions={"get": "retrieve"})
        response = view(request, pk=instance_id)
        return response

    def get_instance_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the InstanceViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get("/instances/", data)
        force_authenticate(request, user=user)
        view = InstanceViewSet.as_view(actions={"get": "list"})
        response = view(request)
        return response

    def get_instance_ids_from_list_response(self, response):
        """
        Get the instance id values from the paginated response.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the instance id values found in the response

        """
        instance_ids = set(
            [instance["instance_id"] for instance in response.data["data"]]
        )
        return instance_ids

    def test_list_instances_as_user1(self):
        """Assert that user1 sees only its own instances."""
        expected_instances = {
            self.instance1.id,
            self.instance2.id,
        }
        response = self.get_instance_list_response(self.user1)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances, actual_instances)

    def test_list_instances_as_user2(self):
        """Assert that user2 sees only its own instances."""
        expected_instances = {
            self.instance3.id,
            self.instance4.id,
        }
        response = self.get_instance_list_response(self.user2)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances, actual_instances)

    def test_get_user1s_instance_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own instances."""
        user = self.user1
        instance = self.instance2  # Instance belongs to user1.

        response = self.get_instance_get_response(user, instance.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasInstanceData(response, instance)

    def test_get_user1s_instance_as_user2_returns_404(self):
        """Assert that user2 cannot get an instance belonging to user1."""
        user = self.user2
        instance = self.instance2  # Instance belongs to user1, NOT user2.

        response = self.get_instance_get_response(user, instance.id)
        self.assertEqual(response.status_code, 404)

    @util_helper.clouditardis(util_helper.utc_dt(2019, 4, 20, 0, 0, 0))
    def test_list_instances_as_user1_with_running_since_filter(self):
        """
        Assert that user1 can only see his/her running instances.

        instance1 (user1/account1) started in 2019-02 and is still running.
        instance2 (user1/account2) started in 2019-03 and has stopped running.
        instance3 (user2/account3) started in 2019-04 and is still running.
        instance4 (user2/account4) has never run.

        Requesting since mid 2016 as user1 should return no instances.
        Requesting since mid 2017 as user1 should return instance1.
        Requesting since mid 2018 as user1 should return instance1.
        Requesting since mid 2019 as user1 should return instance1.
        """
        # Generate activity for instances
        api_helper.generate_single_run(
            self.instance1,
            (util_helper.utc_dt(2019, 2, 2, 0, 0, 0), None),
        )

        api_helper.generate_single_run(
            self.instance2,
            (
                util_helper.utc_dt(2019, 3, 1, 0, 0, 0),
                util_helper.utc_dt(2019, 3, 2, 0, 0, 0),
            ),
        )

        api_helper.generate_single_run(
            self.instance3,
            (util_helper.utc_dt(2019, 4, 1, 0, 0, 0), None),
        )

        mid_2019_01 = util_helper.utc_dt(2019, 1, 15, 0, 0, 0)
        mid_2019_02 = util_helper.utc_dt(2019, 2, 15, 0, 0, 0)
        mid_2019_03 = util_helper.utc_dt(2019, 3, 15, 0, 0, 0)
        mid_2019_04 = util_helper.utc_dt(2019, 4, 15, 0, 0, 0)
        expected_instances_since_mid_2019_01 = set()
        expected_instances_since_mid_2019_02 = {self.instance1.id}
        expected_instances_since_mid_2019_03 = {self.instance1.id}
        expected_instances_since_mid_2019_04 = {self.instance1.id}

        params = {"running_since": mid_2019_01}
        response = self.get_instance_list_response(self.user1, params)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances_since_mid_2019_01, actual_instances)

        params = {"running_since": mid_2019_02}
        response = self.get_instance_list_response(self.user1, params)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances_since_mid_2019_02, actual_instances)

        params = {"running_since": mid_2019_03}
        response = self.get_instance_list_response(self.user1, params)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances_since_mid_2019_03, actual_instances)

        params = {"running_since": mid_2019_04}
        response = self.get_instance_list_response(self.user1, params)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances_since_mid_2019_04, actual_instances)
