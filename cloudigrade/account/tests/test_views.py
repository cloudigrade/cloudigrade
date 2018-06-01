"""Collection of tests for custom DRF views in the account app."""
from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework import exceptions, status
from rest_framework.test import APIRequestFactory, force_authenticate

from account import AWS_PROVIDER_STRING
from account.exceptions import InvalidCloudProviderError
from account.models import (AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage)
from account.tests import helper as account_helper
from account.views import (AccountViewSet,
                           InstanceEventViewSet,
                           InstanceViewSet,
                           MachineImageViewSet,
                           ReportViewSet)
from util.tests import helper as util_helper


class ReportViewSetTest(TestCase):
    """ReportViewSet test case."""

    def test_create_report_success(self):
        """Test report succeeds when given appropriate values."""
        mock_request = Mock()
        mock_request.data = {
            'cloud_provider': AWS_PROVIDER_STRING,
            'cloud_account_id': util_helper.generate_dummy_aws_account_id(),
            'start': '2018-01-01T00:00:00',
            'end': '2018-02-01T00:00:00',
        }
        view = ReportViewSet()
        with patch.object(view, 'serializer_class') as mock_serializer_class:
            report_results = mock_serializer_class.return_value\
                .generate.return_value
            response = view.list(mock_request)
            self.assertEqual(response.data, report_results)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_create_404s_missing_account(self):
        """Test report 404s when requesting an account that doesn't exist."""
        mock_request = Mock()
        mock_request.data = {
            'cloud_provider': AWS_PROVIDER_STRING,
            'cloud_account_id': util_helper.generate_dummy_aws_account_id(),
            'start': '2018-01-01T00:00:00',
            'end': '2018-02-01T00:00:00',
        }
        view = ReportViewSet()
        with patch.object(view, 'serializer_class') as mock_serializer_class:
            mock_serializer_class.return_value.generate = \
                Mock(side_effect=AwsAccount.DoesNotExist())
            with self.assertRaises(exceptions.NotFound):
                view.list(mock_request)

    def test_create_400s_unrecognized_cloud_provider(self):
        """Test report 400s when requesting an unrecognized cloud provider."""
        mock_request = Mock()
        mock_request.data = {
            'cloud_provider': AWS_PROVIDER_STRING,
            'cloud_account_id': util_helper.generate_dummy_aws_account_id(),
            'start': '2018-01-01T00:00:00',
            'end': '2018-02-01T00:00:00',
        }
        view = ReportViewSet()
        with patch.object(view, 'serializer_class') as mock_serializer_class:
            mock_serializer_class.return_value.generate = \
                Mock(side_effect=InvalidCloudProviderError())
            with self.assertRaises(exceptions.ValidationError):
                view.list(mock_request)


class AccountViewSetTest(TestCase):
    """AccountViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)
        self.account1 = account_helper.generate_aws_account(user=self.user1)
        self.account2 = account_helper.generate_aws_account(user=self.user1)
        self.account3 = account_helper.generate_aws_account(user=self.user2)
        self.account4 = account_helper.generate_aws_account(user=self.user2)
        self.factory = APIRequestFactory()

    def assertResponseHasAwsAccountData(self, response, account):
        """Assert the response has data matching the account object."""
        self.assertEqual(
            response.data['id'], account.id
        )
        self.assertEqual(
            response.data['user_id'], account.user_id
        )
        self.assertEqual(
            response.data['resourcetype'], account.__class__.__name__
        )

        if isinstance(account, AwsAccount):
            self.assertEqual(
                response.data['account_arn'], account.account_arn
            )
            self.assertEqual(
                response.data['aws_account_id'], account.aws_account_id
            )

    def get_aws_account_ids_from_list_response(self, response):
        """
        Get the aws_account_id values from the paginated response.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the aws_account_id values found in the response

        """
        aws_account_ids = set([
            account['aws_account_id'] for account in response.data['results']
        ])
        return aws_account_ids

    def get_account_get_response(self, user, account_id):
        """
        Generate a response for a get-retrieve on the AccountViewSet.

        Args:
            user (User): Django auth user performing the request
            account_id (int): the id of the account to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/account/')
        force_authenticate(request, user=user)
        view = AccountViewSet.as_view(actions={'get': 'retrieve'})
        response = view(request, pk=account_id)
        return response

    def get_account_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the AccountViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/account/', data)
        force_authenticate(request, user=user)
        view = AccountViewSet.as_view(actions={'get': 'list'})
        response = view(request)
        return response

    def test_list_accounts_as_user1(self):
        """Assert that user1 sees only its own accounts."""
        expected_accounts = {
            self.account1.aws_account_id,
            self.account2.aws_account_id,
        }
        response = self.get_account_list_response(self.user1)
        actual_accounts = self.get_aws_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_list_accounts_as_user2(self):
        """Assert that user2 sees only its own accounts."""
        expected_accounts = {
            self.account3.aws_account_id,
            self.account4.aws_account_id,
        }
        response = self.get_account_list_response(self.user2)
        actual_accounts = self.get_aws_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_list_accounts_as_superuser(self):
        """Assert that the superuser sees all accounts regardless of owner."""
        expected_accounts = {
            self.account1.aws_account_id,
            self.account2.aws_account_id,
            self.account3.aws_account_id,
            self.account4.aws_account_id
        }
        response = self.get_account_list_response(self.superuser)
        actual_accounts = self.get_aws_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_list_accounts_as_superuser_with_filter(self):
        """Assert that the superuser sees accounts filtered by user_id."""
        expected_accounts = {
            self.account3.aws_account_id,
            self.account4.aws_account_id
        }
        params = {'user_id': self.user2.id}
        response = self.get_account_list_response(self.superuser, params)
        actual_accounts = self.get_aws_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_list_accounts_as_superuser_with_bad_filter(self):
        """Assert that the list accounts returns 400 with bad user_id."""
        params = {'user_id': 'not_an_int'}
        response = self.get_account_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)

    def test_get_user1s_account_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own accounts."""
        user = self.user1
        account = self.account2  # Account belongs to user1.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAwsAccountData(response, account)

    def test_get_user1s_account_as_user2_returns_404(self):
        """Assert that user2 cannot get an account belonging to user1."""
        user = self.user2
        account = self.account2  # Account belongs to user1, NOT user2.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 404)

    def test_get_user1s_account_as_superuser_returns_ok(self):
        """Assert that superuser can get another user's accounts."""
        user = self.superuser
        account = self.account2  # Account belongs to user1, NOT superuser.

        response = self.get_account_get_response(user, account.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasAwsAccountData(response, account)


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
            response.data['resourcetype'], instance.__class__.__name__
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


class MachineImageViewSetTest(TestCase):
    """MachineImageViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)
        self.account1 = account_helper.generate_aws_account(user=self.user1)
        self.account2 = account_helper.generate_aws_account(user=self.user1)
        self.account3 = account_helper.generate_aws_account(user=self.user2)
        self.account4 = account_helper.generate_aws_account(user=self.user2)
        self.machine_image1 = \
            account_helper.generate_aws_image(account=self.account1)
        self.machine_image2 = \
            account_helper.generate_aws_image(account=self.account2)
        self.machine_image3 = \
            account_helper.generate_aws_image(account=self.account3)
        self.machine_image4 = \
            account_helper.generate_aws_image(account=self.account4)
        self.factory = APIRequestFactory()

    def assertResponseHasImageData(self, response, image):
        """Assert the response has data matching the image object."""
        self.assertEqual(
            response.data['id'], image.id
        )
        self.assertEqual(
            response.data['account'],
            f'http://testserver/api/v1/account/{image.account.id}/'
        )
        self.assertEqual(
            response.data['resourcetype'], image.__class__.__name__
        )

        if isinstance(image, AwsMachineImage):
            self.assertEqual(
                response.data['ec2_ami_id'], image.ec2_ami_id
            )
            self.assertEqual(
                response.data['is_encrypted'], image.is_encrypted
            )

    def get_image_get_response(self, user, image_id):
        """
        Generate a response for a get-retrieve on the MachineImageViewSet.

        Args:
            user (User): Django auth user performing the request
            image_id (int): the id of the image to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/image/')
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={'get': 'retrieve'})
        response = view(request, pk=image_id)
        return response

    def get_image_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the MachineImageViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/image/', data)
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={'get': 'list'})
        response = view(request)
        return response

    def get_image_ids_from_list_response(self, response):
        """
        Get the image id values from the paginated response.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the image id values found in the response

        """
        image_ids = set([
            image['id'] for image in response.data['results']
        ])
        return image_ids

    def test_list_images_as_user1(self):
        """Assert that user1 sees only its own images."""
        expected_images = {
            self.machine_image1.id,
            self.machine_image2.id,
        }
        response = self.get_image_list_response(self.user1)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_as_user2(self):
        """Assert that user2 sees only its own images."""
        expected_images = {
            self.machine_image3.id,
            self.machine_image4.id,
        }
        response = self.get_image_list_response(self.user2)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_as_superuser(self):
        """Assert that the superuser sees all images regardless of owner."""
        expected_images = {
            self.machine_image1.id,
            self.machine_image2.id,
            self.machine_image3.id,
            self.machine_image4.id
        }
        response = self.get_image_list_response(self.superuser)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_as_superuser_with_filter(self):
        """Assert that the superuser sees images filtered by user_id."""
        expected_images = {
            self.machine_image3.id,
            self.machine_image4.id
        }
        params = {'user_id': self.user2.id}
        response = self.get_image_list_response(self.superuser, params)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_get_user1s_image_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own images."""
        user = self.user1
        image = self.machine_image2  # Image belongs to user1.

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasImageData(response, image)

    def test_get_user1s_image_as_user2_returns_404(self):
        """Assert that user2 cannot get an image belonging to user1."""
        user = self.user2
        image = self.machine_image2  # Image belongs to user1, NOT user2.

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 404)

    def test_get_user1s_image_as_superuser_returns_ok(self):
        """Assert that superuser can get another user's images."""
        user = self.superuser
        # Image belongs to user1, NOT superuser.
        image = self.machine_image2

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasImageData(response, image)

    def test_list_images_as_superuser_with_bad_filter(self):
        """Assert that the list images returns 400 with bad user_id."""
        params = {'user_id': 'not_an_int'}
        response = self.get_image_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)


class InstanceEventViewSetTest(TestCase):
    """InstanceEventViewSet test case."""

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
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
        self.event1 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance1, powered_time=powered_time)
        self.event2 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance2, powered_time=powered_time)
        self.event3 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance3, powered_time=powered_time)
        self.event4 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance4, powered_time=powered_time)
        self.factory = APIRequestFactory()

    def assertResponseHasEventData(self, response, event):
        """Assert the response has data matching the instance event object."""
        self.assertEqual(
            response.data['id'], event.id
        )
        self.assertEqual(
            response.data['instance'],
            f'http://testserver/api/v1/instance/{event.instance.id}/'
        )
        self.assertEqual(
            response.data['resourcetype'], event.__class__.__name__
        )

        if isinstance(event, AwsInstanceEvent):
            self.assertEqual(
                response.data['subnet'], event.subnet
            )
            self.assertEqual(
                response.data['ec2_ami_id'], event.ec2_ami_id
            )
            self.assertEqual(
                response.data['event_type'], event.event_type
            )
            self.assertEqual(
                response.data['instance_type'], event.instance_type
            )

    def get_event_get_response(self, user, event_id):
        """
        Generate a response for a get-retrieve on the InstanceViewSet.

        Args:
            user (User): Django auth user performing the request
            event_id (int): the id of the instance event to retrieve
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/event/')
        force_authenticate(request, user=user)
        view = InstanceEventViewSet.as_view(actions={'get': 'retrieve'})
        response = view(request, pk=event_id)
        return response

    def get_event_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the InstanceEventViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/event/', data)
        force_authenticate(request, user=user)
        view = InstanceEventViewSet.as_view(actions={'get': 'list'})
        response = view(request)
        return response

    def get_event_ids_from_list_response(self, response):
        """
        Get the instance event id values from the paginated response.

        Args:
            response (Response): Django response object to inspect

        Returns:
            set[int]: the event id values found in the response

        """
        event_ids = set([
            event['id'] for event in response.data['results']
        ])
        return event_ids

    def test_list_events_as_user1(self):
        """Assert that user1 sees only its own instance events."""
        expected_events = {
            self.event1.id,
            self.event2.id,
        }
        response = self.get_event_list_response(self.user1)
        actual_events = \
            self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_user2(self):
        """Assert that user2 sees only its own instance events."""
        expected_events = {
            self.event3.id,
            self.event4.id,
        }
        response = self.get_event_list_response(self.user2)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_superuser(self):
        """Assert that the superuser sees all events regardless of owner."""
        expected_events = {
            self.event1.id,
            self.event2.id,
            self.event3.id,
            self.event4.id
        }
        response = self.get_event_list_response(self.superuser)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_superuser_with_user_filter(self):
        """Assert that the superuser sees events filtered by user_id."""
        expected_events = {
            self.event3.id,
            self.event4.id
        }
        params = {'user_id': self.user2.id}
        response = self.get_event_list_response(self.superuser, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_superuser_with_instance_filter(self):
        """Assert that the superuser sees events filtered by instance_id."""
        expected_events = {
            self.event3.id,
        }
        params = {'instance_id': self.instance3.id}
        response = self.get_event_list_response(self.superuser, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_user1_with_instance_filter(self):
        """Assert that the user1 sees user1 events filtered by instance_id."""
        expected_events = {
            self.event1.id,
        }
        params = {'instance_id': self.instance1.id}
        response = self.get_event_list_response(self.user1, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_list_events_as_user2_with_instance_filter(self):
        """Assert that the user2 sees user2 events filtered by instance_id."""
        expected_events = {
            self.event3.id,
        }
        params = {'instance_id': self.instance3.id}
        response = self.get_event_list_response(self.user2, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)

    def test_get_user1s_event_as_user1_returns_ok(self):
        """Assert that user1 can get one of its own events."""
        user = self.user1
        event = self.event2  # Event belongs to user1.

        response = self.get_event_get_response(user, event.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasEventData(response, event)

    def test_get_user1s_event_as_user2_returns_404(self):
        """Assert that user2 cannot get an event belonging to user1."""
        user = self.user2
        event = self.event2  # Event belongs to user1, NOT user2.

        response = self.get_event_get_response(user, event.id)
        self.assertEqual(response.status_code, 404)

    def test_get_user1s_event_as_superuser_returns_ok(self):
        """Assert that superuser can get another user's events."""
        user = self.superuser
        event = self.event2  # Instance belongs to user1, NOT superuser.

        response = self.get_event_get_response(user, event.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasEventData(response, event)

    def test_list_events_as_superuser_with_bad_filter(self):
        """Assert that the list events returns 400 with bad user_id."""
        params = {'user_id': 'not_an_int'}
        response = self.get_event_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)

    def test_list_events_as_superuser_with_user_and_instance_filters(self):
        """Assert that super user can stack instance & user filters."""
        expected_events = {
            self.event3.id,
        }
        params = {'instance_id': self.instance3.id,
                  'user_id': self.user2.id}
        response = self.get_event_list_response(self.superuser, params)
        actual_events = self.get_event_ids_from_list_response(response)
        self.assertEqual(expected_events, actual_events)
