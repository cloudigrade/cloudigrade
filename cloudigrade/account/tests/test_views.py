"""Collection of tests for custom DRF views in the account app."""
from unittest.mock import Mock, patch

import faker
from django.test import TestCase
from rest_framework import exceptions, status
from rest_framework.test import APIRequestFactory, force_authenticate

from account import AWS_PROVIDER_STRING
from account import views
from account.exceptions import InvalidCloudProviderError
from account.models import (AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage,
                            ImageTag,
                            InstanceEvent)
from account.tests import helper as account_helper
from account.views import (AccountViewSet,
                           CloudAccountOverviewViewSet,
                           InstanceEventViewSet,
                           InstanceViewSet,
                           MachineImageViewSet,
                           ReportViewSet,
                           SysconfigViewSet)
from util.aws import AwsArn
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
        self.faker = faker.Faker()

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
        self.assertEqual(
            response.data['name'], account.name
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

    @patch.object(views.serializers, 'aws')
    def test_create_account_with_name_success(self, mock_aws):
        """Test create account with a name succeeds."""
        mock_aws.verify_account_access.return_value = True, []
        mock_aws.AwsArn = AwsArn

        data = {
            'resourcetype': 'AwsAccount',
            'account_arn': util_helper.generate_dummy_arn(),
            'name': faker.Faker().bs()[:256],
        }

        request = self.factory.post('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(actions={'post': 'create'})
        response = view(request)

        self.assertEqual(response.status_code, 201)
        for key, value in data.items():
            self.assertEqual(response.data[key], value)
        self.assertIsNotNone(response.data['name'])

    @patch.object(views.serializers, 'aws')
    def test_create_account_without_name_success(self, mock_aws):
        """Test create account without a name succeeds."""
        mock_aws.verify_account_access.return_value = True, []
        mock_aws.AwsArn = AwsArn

        data = {
            'resourcetype': 'AwsAccount',
            'account_arn': util_helper.generate_dummy_arn(),
        }

        request = self.factory.post('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(actions={'post': 'create'})
        response = view(request)

        self.assertEqual(response.status_code, 201)
        for key, value in data.items():
            self.assertEqual(response.data[key], value)
        self.assertIsNone(response.data['name'])

    def test_update_account_patch_name_success(self):
        """Test updating an account with a name succeeds."""
        data = {
            'resourcetype': 'AwsAccount',
            'name': faker.Faker().bs()[:256],
        }

        account_id = self.account4.id
        request = self.factory.patch('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(
            actions={'patch': 'partial_update'}
        )
        response = view(request, pk=account_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data['name'], response.data['name'])

    def test_update_account_patch_arn_fails(self):
        """Test that updating to change the arn fails."""
        data = {
            'resourcetype': 'AwsAccount',
            'account_arn': util_helper.generate_dummy_arn(),
        }

        account_id = self.account4.id
        request = self.factory.patch('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(
            actions={'patch': 'partial_update'}
        )
        response = view(request, pk=account_id)

        self.assertEqual(response.status_code, 400)

    def test_create_with_malformed_arn_fails(self):
        """Test create account with malformed arn returns validation error."""
        data = {
            'resourcetype': 'AwsAccount',
            'account_arn': self.faker.bs(),
        }

        request = self.factory.post('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(actions={'post': 'create'})
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn('account_arn', response.data)


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
            account_helper.generate_aws_image(account=self.account4,
                                              is_windows=True)
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

    def test_marking_images_as_windows_tags_them_as_windows(self):
        """Assert that creating a windows image tags it appropriately."""
        image = self.machine_image4  # Image was created as is_windows
        self.assertEqual(image.tags.filter(description='windows').first(),
                         ImageTag.objects.filter(
                             description='windows').first())


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


class SysconfigViewSetTest(TestCase):
    """SysconfigViewSet test case."""

    @patch('account.views._get_primary_account_id')
    def test_list_accounts_success(self, mock_get_primary_account_id):
        """Test listing account ids."""
        account_id = account_helper.generate_aws_account()
        mock_get_primary_account_id.return_value = account_id
        user = util_helper.generate_test_user()
        factory = APIRequestFactory()
        request = factory.get('/sysconfig/')
        force_authenticate(request, user=user)
        view = SysconfigViewSet.as_view(actions={'get': 'list'})

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'aws_account_id': account_id})


class CloudAccountOverviewViewSetTest(TestCase):
    """CloudAccountOverviewViewSet test case."""

    def setUp(self):
        """Set up a bunch of test data."""
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)
        powered_time = util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
        self.superuser = util_helper.generate_test_user(is_superuser=True)
        self.account1 = account_helper.generate_aws_account(user=self.user1)
        self.account1.created_at = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.account1.save()
        self.account2 = account_helper.generate_aws_account(user=self.user1)
        self.account2.created_at = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.account2.save()
        self.account3 = account_helper.generate_aws_account(user=self.user2)
        self.account3.created_at = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.account3.save()
        self.account4 = account_helper.generate_aws_account(user=self.user2)
        self.account4.created_at = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.account4.save()
        self.instance1 = \
            account_helper.generate_aws_instance(account=self.account1)
        self.instance2 = \
            account_helper.generate_aws_instance(account=self.account2)
        self.instance3 = \
            account_helper.generate_aws_instance(account=self.account3)
        self.instance4 = \
            account_helper.generate_aws_instance(account=self.account4)
        self.windows_image = account_helper.generate_aws_image(
            self.account1,
            is_encrypted=False,
            is_windows=True,
        )
        self.rhel_image = account_helper.generate_aws_image(
            self.account2,
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            is_rhel=True,
            is_openshift=False)
        self.openshift_image = account_helper.generate_aws_image(
            self.account3,
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            is_rhel=False,
            is_openshift=True)
        self.openshift_and_rhel_image = account_helper.generate_aws_image(
            self.account4,
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            is_rhel=True,
            is_openshift=True)
        self.event1 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance1, powered_time=powered_time,
                event_type=InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.windows_image.ec2_ami_id)
        self.event2 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance2, powered_time=powered_time,
                event_type=InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.rhel_image.ec2_ami_id)
        self.event3 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance3, powered_time=powered_time,
                event_type=InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.openshift_image.ec2_ami_id)
        self.event4 = \
            account_helper.generate_single_aws_instance_event(
                instance=self.instance4, powered_time=powered_time,
                event_type=InstanceEvent.TYPE.power_on,
                ec2_ami_id=self.openshift_and_rhel_image.ec2_ami_id)
        self.factory = APIRequestFactory()
        self.account1_expected_overview = {
            'id': self.account1.aws_account_id,
            'user_id': self.account1.user_id,
            'type': 'aws',
            'arn': self.account1.account_arn,
            'creation_date': self.account1.created_at,
            'name': self.account1.name,
            'images': 1,
            'instances': 1,
            'rhel_instances': 0,
            'openshift_instances': 0}
        self.account2_expected_overview = {
            'id': self.account2.aws_account_id,
            'user_id': self.account2.user_id,
            'type': 'aws',
            'arn': self.account2.account_arn,
            'creation_date': self.account2.created_at,
            'name': self.account2.name,
            'images': 1,
            'instances': 1,
            'rhel_instances': 1,
            'openshift_instances': 0}
        self.account3_expected_overview = {
            'id': self.account3.aws_account_id,
            'user_id': self.account3.user_id,
            'type': 'aws',
            'arn': self.account3.account_arn,
            'creation_date': self.account3.created_at,
            'name': self.account3.name,
            'images': 1,
            'instances': 1,
            'rhel_instances': 0,
            'openshift_instances': 1}
        self.account4_expected_overview = {
            'id': self.account4.aws_account_id,
            'user_id': self.account4.user_id,
            'type': 'aws',
            'arn': self.account4.account_arn,
            'creation_date': self.account4.created_at,
            'name': self.account4.name,
            'images': 1,
            'instances': 1,
            'rhel_instances': 1,
            'openshift_instances': 1}

    def get_overview_list_response(self, user, data=None):
        """
        Generate a response for a get-list on the InstanceEventViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params

        Returns:
            Response: the generated response for this request

        """
        if data is None:
            # start and end date are required
            data = {'start': self.start,
                    'end': self.end
                    }

        request = self.factory.get('/report/accounts/', data)
        force_authenticate(request, user=user)
        view = CloudAccountOverviewViewSet.as_view(actions={'get': 'list'})
        response = view(request)
        return response

    def test_list_overviews_as_superuser(self):
        """Assert that the superuser sees all overviews regardless of owner."""
        expected_response = {
            'cloud_account_overviews': [
                self.account1_expected_overview,
                self.account2_expected_overview,
                self.account3_expected_overview,
                self.account4_expected_overview
            ]
        }
        response = self.get_overview_list_response(self.superuser)
        actual_response = response.data
        self.assertEqual(expected_response, actual_response)

    def test_list_overviews_as_user1(self):
        """Assert that the user1 sees only overviews of user1 accounts."""
        expected_response = {
            'cloud_account_overviews': [
                self.account1_expected_overview,
                self.account2_expected_overview,
            ]
        }
        response = self.get_overview_list_response(self.user1)
        actual_response = response.data
        self.assertEqual(expected_response, actual_response)

    def test_list_overviews_as_user2(self):
        """Assert that the user2 sees only overviews of user2 accounts."""
        expected_response = {
            'cloud_account_overviews': [
                self.account3_expected_overview,
                self.account4_expected_overview,
            ]
        }
        response = self.get_overview_list_response(self.user2)
        actual_response = response.data
        self.assertEqual(expected_response, actual_response)

    def test_get_user1s_overview_as_superuser_returns_ok(self):
        """Assert that superuser can get another user's overviews."""
        expected_response = {
            'cloud_account_overviews': [
                self.account1_expected_overview,
                self.account2_expected_overview,
            ]
        }
        params = {'user_id': self.user1.id,
                  'start': self.start,
                  'end': self.end
                  }
        response = self.get_overview_list_response(self.superuser, params)
        actual_response = response.data
        self.assertEqual(expected_response, actual_response)

    def test_list_overviews_as_superuser_with_bad_filter(self):
        """Assert that the list overviews returns 400 with bad start & end."""
        params = {'start': 'January 1',
                  'end': 'February 1'}
        response = self.get_overview_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)
