"""Collection of tests for AccountViewSet."""
from unittest.mock import patch

import faker
from django.test import TestCase
from rest_framework.test import (APIRequestFactory,
                                 force_authenticate)

from account import views
from account.models import (AwsAccount)
from account.tests import helper as account_helper
from account.views import (AccountViewSet)
from util.aws import AwsArn
from util.tests import helper as util_helper


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
        self.account5 = account_helper.generate_aws_account(user=self.user2,
                                                            name='unique')
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
        self.assertEqual(
            response.data['url'],
            f'http://testserver/api/v1/account/{account.id}/'
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
            self.account5.aws_account_id,
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
            self.account4.aws_account_id,
            self.account5.aws_account_id
        }
        response = self.get_account_list_response(self.superuser)
        actual_accounts = self.get_aws_account_ids_from_list_response(response)
        self.assertEqual(expected_accounts, actual_accounts)

    def test_list_accounts_as_superuser_with_filter(self):
        """Assert that the superuser sees accounts filtered by user_id."""
        expected_accounts = {
            self.account3.aws_account_id,
            self.account4.aws_account_id,
            self.account5.aws_account_id
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
    @patch.object(views.serializers, 'tasks')
    def test_create_account_with_name_success(self, mock_tasks, mock_aws):
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
        mock_tasks.initial_aws_describe_instances.delay.assert_called()

    @patch.object(views.serializers, 'aws')
    @patch.object(views.serializers, 'tasks')
    def test_create_account_with_duplicate_name_fail(self, mock_tasks,
                                                     mock_aws):
        """Test create account with a duplicate name fails."""
        mock_aws.verify_account_access.return_value = True, []
        mock_aws.AwsArn = AwsArn

        data = {
            'resourcetype': 'AwsAccount',
            'account_arn': util_helper.generate_dummy_arn(),
            'name': 'unique',
        }

        request = self.factory.post('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(actions={'post': 'create'})
        response = view(request)

        self.assertEqual(response.status_code, 400)
        self.assertIn('non_field_errors', response.data)
        mock_tasks.initial_aws_describe_instances.delay.assert_not_called()

    @patch.object(views.serializers, 'aws')
    @patch.object(views.serializers, 'tasks')
    def test_create_account_without_name_fail(self, mock_tasks, mock_aws):
        """Test create account without a name fails."""
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

        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.data)
        mock_tasks.initial_aws_describe_instances.delay.assert_not_called()

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

    def test_update_account_patch_duplicate_name_fail(self):
        """Test updating an account with a duplicate name fails."""
        data = {
            'resourcetype': 'AwsAccount',
            'name': 'unique',
        }

        account_id = self.account3.id
        request = self.factory.patch('/account/', data=data)
        force_authenticate(request, user=self.user2)

        view = views.AccountViewSet.as_view(
            actions={'patch': 'partial_update'}
        )
        response = view(request, pk=account_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn('non_field_errors', response.data)

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
