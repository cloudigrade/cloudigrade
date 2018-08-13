"""Collection of tests for CloudAccountOverviewViewSet."""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from account.models import (InstanceEvent)
from account.tests import helper as account_helper
from account.views import (CloudAccountOverviewViewSet)
from util.tests import helper as util_helper


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

        # These names are not randomly generated because we need to test
        # against specific combinations of names.
        self.name1 = 'greatest account ever'
        self.name2 = 'this account is just okay'

        self.account1 = account_helper.generate_aws_account(user=self.user1,
                                                            name=self.name1)
        self.account1.created_at = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.account1.save()
        self.account2 = account_helper.generate_aws_account(user=self.user1,
                                                            name=self.name2)
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
            is_encrypted=False,
            is_windows=True)
        self.rhel_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=True,
            openshift_detected=False)
        self.openshift_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=False,
            openshift_detected=True)
        self.openshift_and_rhel_image = account_helper.generate_aws_image(
            is_encrypted=False,
            is_windows=False,
            ec2_ami_id=None,
            rhel_detected=True,
            openshift_detected=True)
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
            'id': self.account1.id,
            'cloud_account_id': self.account1.aws_account_id,
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
            'id': self.account2.id,
            'cloud_account_id': self.account2.aws_account_id,
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
            'id': self.account3.id,
            'cloud_account_id': self.account3.aws_account_id,
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
            'id': self.account4.id,
            'cloud_account_id': self.account4.aws_account_id,
            'user_id': self.account4.user_id,
            'type': 'aws',
            'arn': self.account4.account_arn,
            'creation_date': self.account4.created_at,
            'name': self.account4.name,
            'images': 1,
            'instances': 1,
            'rhel_instances': 1,
            'openshift_instances': 1}

    def get_overview_list_response(self, user, data=None, name_pattern=None,
                                   account_id=None):
        """
        Generate a response for a get-list on the InstanceEventViewSet.

        Args:
            user (User): Django auth user performing the request
            data (dict): optional data to use as query params
            name_pattern (string): optional name_filter to use for query param
            account_id (int): optional account_id to filter against

        Returns:
            Response: the generated response for this request

        """
        if data is None:
            # start and end date are required
            data = {
                'start': self.start,
                'end': self.end,
            }
        if name_pattern:
            data['name_pattern'] = name_pattern
        if account_id:
            data['account_id'] = account_id

        request = self.factory.get('/report/accounts/', data)
        force_authenticate(request, user=user)
        view = CloudAccountOverviewViewSet.as_view(actions={'get': 'list'})
        response = view(request)
        return response

    def test_list_overviews_as_superuser(self):
        """Assert that the superuser sees its own accounts overviews."""
        expected_response = {
            'cloud_account_overviews': [
                # The data in setUp belongs to all of the other users.
                # So, when the superuser requests, it gets an empty set here.
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

    def test_list_overviews_as_user1_name_filter_to_one(self):
        """Assert that the user1 sees one account filtered by name."""
        expected_response = {
            'cloud_account_overviews': [
                self.account1_expected_overview,
            ]
        }
        response = self.get_overview_list_response(self.user1,
                                                   name_pattern='greatest')
        actual_response = response.data
        self.assertEqual(expected_response, actual_response)

    def test_list_overviews_as_user1_name_filter_to_multiple(self):
        """Assert that the user1 sees multiple accounts filtered by name."""
        expected_response = {
            'cloud_account_overviews': [
                self.account1_expected_overview,
                self.account2_expected_overview,
            ]
        }
        response = self.get_overview_list_response(self.user1,
                                                   name_pattern='account')
        actual_response = response.data
        self.assertEqual(expected_response, actual_response)

    def test_list_overviews_as_user1_name_filter_to_none(self):
        """Assert that the user1 sees zero accounts filtered by name."""
        expected_response = {
            'cloud_account_overviews': []
        }
        response = self.get_overview_list_response(self.user1,
                                                   name_pattern='bananas')
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

    def test_get_user1_account1_overview(self):
        """Assert that user1 can see a specific account belonging to them."""
        expected_response = {
            'cloud_account_overviews': [
                self.account1_expected_overview
            ]
        }
        params = {
            'account_id': self.account1.id,
            'user_id': self.user1.id,
            'start': self.start,
            'end': self.end
        }
        response = self.get_overview_list_response(self.user1, params)
        self.assertEqual(expected_response, response.data)

    def test_get_user2_account3_as_user1_returns_empty(self):
        """Assert that user1 can't see specific account belonging to user2."""
        expected_response = {
            'cloud_account_overviews': []
        }
        params = {
            'account_id': self.account3.id,
            'user_id': self.user2.id,
            'start': self.start,
            'end': self.end
        }
        response = self.get_overview_list_response(self.user1, params)
        self.assertEqual(expected_response, response.data)

    def test_get_user2_account3_as_superuser_returns_ok(self):
        """Assert that superuser can see account belonging to user2."""
        expected_response = {
            'cloud_account_overviews': [
                self.account3_expected_overview
            ]
        }
        params = {
            'account_id': self.account3.id,
            'user_id': self.user2.id,
            'start': self.start,
            'end': self.end
        }
        response = self.get_overview_list_response(self.superuser, params)
        self.assertEqual(expected_response, response.data)
