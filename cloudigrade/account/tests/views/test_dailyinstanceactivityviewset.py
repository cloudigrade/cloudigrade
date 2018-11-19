"""Collection of tests for DailyInstanceActivityViewSet."""
import uuid

import faker
from django.test import TestCase
from rest_framework.test import (APIClient)

from account.tests import helper as account_helper
from util.tests import helper as util_helper


class DailyInstanceActivityViewSetTest(TestCase):
    """DailyInstanceActivityViewSet test case."""

    def setUp(self):
        """Set up commonly used data for each test."""
        # Users
        self.user = util_helper.generate_test_user()
        self.other_user = util_helper.generate_test_user()
        self.multi_account_user = util_helper.generate_test_user()
        self.super_user = util_helper.generate_test_user(is_superuser=True)

        # Clounts
        self.account = account_helper.generate_aws_account(
            user=self.user, name=faker.Faker().bs())
        self.u3_first_account = account_helper.generate_aws_account(
            user=self.multi_account_user, name=faker.Faker().bs())
        self.u3_second_account = account_helper.generate_aws_account(
            user=self.multi_account_user, name=faker.Faker().bs())

        # Instances
        self.u1a1_instance_rhel = account_helper.generate_aws_instance(
            self.account)
        self.u1a1_instance_oc = account_helper.generate_aws_instance(
            self.account)
        self.u3a1_instance_rhel = account_helper.generate_aws_instance(
            self.u3_first_account)
        self.u3a1_instance_oc = account_helper.generate_aws_instance(
            self.u3_first_account)
        self.u3a2_instance_rhel = account_helper.generate_aws_instance(
            self.u3_second_account)
        self.u3a2_instance_oc = account_helper.generate_aws_instance(
            self.u3_second_account)

        # Images
        self.image_plain = account_helper.generate_aws_image()
        self.image_rhel = account_helper.generate_aws_image(
            rhel_detected=True, openshift_detected=False)
        self.u3a1_image_rhel = account_helper.generate_aws_image(
            rhel_detected=True, openshift_detected=False)
        self.u3a2_image_rhel = account_helper.generate_aws_image(
            rhel_detected=True, openshift_detected=False)
        self.image_os = account_helper.generate_aws_image(
            rhel_detected=False, openshift_detected=True)
        self.image_rhel_openshift = account_helper.generate_aws_image(
            rhel_detected=True, openshift_detected=True)

        # Generate activity for instances belonging to
        # self.user and self.multi_account_user
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 2, 19, 0, 0),
                util_helper.utc_dt(2018, 1, 4, 5, 0, 0)
            ),
        )
        account_helper.generate_aws_instance_events(
            self.u1a1_instance_rhel,
            powered_times,
            ec2_ami_id=self.image_rhel.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            self.u3a1_instance_rhel,
            powered_times,
            ec2_ami_id=self.u3a1_image_rhel.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            self.u3a2_instance_rhel,
            powered_times,
            ec2_ami_id=self.u3a2_image_rhel.ec2_ami_id,
        )

        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)
        account_helper.generate_aws_ec2_definitions()

    def get_report_response(self, as_user, start, end, user_id=None,
                            name_pattern=None, account_id=None):
        """
        Get the daily instance activity API response for the given inputs.

        Args:
            as_user (User): Django auth user performing the request
            start (datetime.datetime): Start time request arg
            end (datetime.datetime): End time request arg
            user_id (int): Optional user_id request arg
            name_pattern (string): Optional name_pattern request arg
            account_id (int): optional account_id to filter against

        Returns:
            Response for this request.

        """
        data = {
            'start': start,
            'end': end,
        }
        if user_id:
            data['user_id'] = user_id
        if name_pattern:
            data['name_pattern'] = name_pattern
        if account_id:
            data['account_id'] = account_id

        client = APIClient()
        client.force_authenticate(user=as_user)
        response = client.get('/api/v1/report/instances/', data, format='json')
        return response

    def assertNoActivity(self, response):
        """Assert report response to include no activity."""
        data = response.json()
        self.assertEqual(data['instances_seen_with_rhel'], 0)
        self.assertEqual(data['instances_seen_with_openshift'], 0)
        self.assertEqual(sum((
            day['rhel_runtime_seconds']
            for day in data['daily_usage']
        )), 0)
        self.assertEqual(sum((
            day['openshift_runtime_seconds']
            for day in data['daily_usage']
        )), 0)

    def assertActivityForRhelInstance(self, response, expected_count=1):
        """Assert report response to include the RHEL instance from setUp."""
        # 122400 is the 34 hours for the powered time in setup.
        expected_hours = 122400.0 * expected_count

        data = response.json()
        self.assertEqual(data['instances_seen_with_rhel'], expected_count)
        self.assertEqual(data['instances_seen_with_openshift'], 0)
        self.assertEqual(sum((
            day['rhel_runtime_seconds']
            for day in data['daily_usage']
        )), expected_hours)
        self.assertEqual(sum((
            day['openshift_runtime_seconds']
            for day in data['daily_usage']
        )), 0)

    def test_no_activity_report_success(self):
        """Assert report data when there is no activity in the period."""
        response = self.get_report_response(self.other_user, self.start,
                                            self.end)
        self.assertNoActivity(response)

    def test_typical_activity_report_success(self):
        """Assert report data when there is some activity in the period."""
        response = self.get_report_response(self.user, self.start, self.end)
        self.assertActivityForRhelInstance(response)

    def test_report_superuser_can_filter_specific_user_success(self):
        """Assert superuser can get activity filtered for another user."""
        response = self.get_report_response(self.super_user, self.start,
                                            self.end, self.user.id)
        self.assertActivityForRhelInstance(response)

    def test_activity_report_with_no_matching_name_filter_success(self):
        """Assert report data excludes not-matching account names."""
        name_pattern = str(uuid.uuid4())
        response = self.get_report_response(self.user, self.start, self.end,
                                            name_pattern=name_pattern)
        self.assertNoActivity(response)

    def test_activity_report_with_matching_name_filter_success(self):
        """Assert report data includes matching account names."""
        name_pattern = self.account.name.split(' ')[2][:3]
        response = self.get_report_response(self.user, self.start, self.end,
                                            name_pattern=name_pattern)
        self.assertActivityForRhelInstance(response)

    def test_user_cannot_filter_to_see_other_user_activity_success(self):
        """Assert one user cannot filter to see data for another user."""
        response = self.get_report_response(self.other_user, self.start,
                                            self.end, user_id=self.user.id)
        self.assertNoActivity(response)

    def test_user_cannot_filter_to_see_other_user_specific_activity(self):
        """Assert that user cannot filter results of another users account."""
        response = self.get_report_response(
            self.other_user, self.start, self.end, self.multi_account_user.id,
            None, self.u3_first_account.id)
        self.assertNoActivity(response)

    def test_super_can_filter_to_see_other_user_activity_success(self):
        """Assert super user can filter to see data for another user."""
        response = self.get_report_response(self.super_user, self.start,
                                            self.end, user_id=self.user.id)
        self.assertActivityForRhelInstance(response)

    def test_super_can_filter_to_see_specific_user_activity_success(self):
        """Assert super user can filter to see specific user account data."""
        response = self.get_report_response(
            self.super_user, self.start, self.end, self.multi_account_user.id,
            None, self.u3_first_account.id)
        self.assertActivityForRhelInstance(response)

    def test_user_can_see_both_accounts(self):
        """Assert report data for one user with multiple accounts."""
        response = self.get_report_response(self.multi_account_user,
                                            self.start, self.end,
                                            self.multi_account_user.id)
        self.assertActivityForRhelInstance(response, 2)

    def test_user_can_filter_to_see_specific_account(self):
        """Assert one user can filter which clount they get data from."""
        response = self.get_report_response(
            self.multi_account_user, self.start, self.end,
            self.multi_account_user.id, None, self.u3_first_account.id)
        self.assertActivityForRhelInstance(response)

        response = self.get_report_response(
            self.multi_account_user, self.start, self.end,
            self.multi_account_user.id, None, self.u3_second_account.id)
        self.assertActivityForRhelInstance(response)
