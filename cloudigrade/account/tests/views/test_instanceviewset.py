"""Collection of tests for InstanceViewSet."""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from account.models import (AwsInstance)
from account.tests import helper as account_helper
from account.views import (InstanceViewSet)
from util.tests import helper as util_helper


class InstanceViewSetTest(TestCase):
    """InstanceViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)
        self.account1 = account_helper.generate_aws_account(user=self.user1)
        self.account2 = account_helper.generate_aws_account(user=self.user1)
        self.account3 = account_helper.generate_aws_account(user=self.user2)
        self.account4 = account_helper.generate_aws_account(user=self.user2)
        self.instance1 = \
            account_helper.generate_aws_instance(account=self.account1)
        self.instance2 = \
            account_helper.generate_aws_instance(account=self.account2)
        self.instance3 = \
            account_helper.generate_aws_instance(account=self.account3)
        self.instance4 = \
            account_helper.generate_aws_instance(account=self.account4)
        self.factory = APIRequestFactory()

    def assertResponseHasInstanceData(self, response, instance):
        """Assert the response has data matching the instance object."""
        self.assertEqual(
            response.data['id'], instance.id
        )
        self.assertEqual(
            response.data['account'],
            f'http://testserver/api/v1/account/{instance.account.id}/'
        )
        self.assertEqual(
            response.data['account_id'], instance.account.id
        )
        self.assertEqual(
            response.data['resourcetype'], instance.__class__.__name__
        )
        self.assertEqual(
            response.data['url'],
            f'http://testserver/api/v1/instance/{instance.id}/'
        )

        if isinstance(instance, AwsInstance):
            self.assertEqual(
                response.data['ec2_instance_id'], instance.ec2_instance_id
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
        request = self.factory.get('/instance/')
        force_authenticate(request, user=user)
        view = InstanceViewSet.as_view(actions={'get': 'retrieve'})
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
        request = self.factory.get('/instance/', data)
        force_authenticate(request, user=user)
        view = InstanceViewSet.as_view(actions={'get': 'list'})
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
        instance_ids = set([
            instance['id'] for instance in response.data['results']
        ])
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

    def test_list_instances_as_superuser(self):
        """Assert that the superuser sees all instances regardless of owner."""
        expected_instances = {
            self.instance1.id,
            self.instance2.id,
            self.instance3.id,
            self.instance4.id
        }
        response = self.get_instance_list_response(self.superuser)
        actual_instances = self.get_instance_ids_from_list_response(response)
        self.assertEqual(expected_instances, actual_instances)

    def test_list_instances_as_superuser_with_filter(self):
        """Assert that the superuser sees instances filtered by user_id."""
        expected_instances = {
            self.instance3.id,
            self.instance4.id
        }
        params = {'user_id': self.user2.id}
        response = self.get_instance_list_response(self.superuser, params)
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

    def test_get_user1s_instance_as_superuser_returns_ok(self):
        """Assert that superuser can get another user's instances."""
        user = self.superuser
        instance = self.instance2  # Instance belongs to user1, NOT superuser.

        response = self.get_instance_get_response(user, instance.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasInstanceData(response, instance)

    def test_list_instances_as_superuser_with_bad_filter(self):
        """Assert that the list instances returns 400 with bad user_id."""
        params = {'user_id': 'not_an_int'}
        response = self.get_instance_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)
