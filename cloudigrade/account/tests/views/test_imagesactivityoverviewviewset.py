"""Collection of tests for ImagesActivityOverviewViewSet."""
import datetime
import operator
from unittest.mock import patch

import faker
from dateutil import tz
from django.test import TestCase
from rest_framework.test import (APIClient,
                                 APIRequestFactory)

from account import views
from account.tests import helper as account_helper
from util.tests import helper as util_helper

HOURS_5 = 60. * 60 * 5


class ImagesActivityOverviewViewSetTestCase(TestCase):
    """ImagesActivityOverviewViewSet test case."""

    def setUp(self):
        """Set up commonly used data for each test."""
        # Users
        self.user = util_helper.generate_test_user()
        self.other_user = util_helper.generate_test_user()
        self.super_user = util_helper.generate_test_user(is_superuser=True)

        # Clounts
        self.account_mixed = account_helper.generate_aws_account(
            user=self.user, name=faker.Faker().bs())
        self.account_none = account_helper.generate_aws_account(
            user=self.user, name=faker.Faker().bs())
        self.account_unknown = account_helper.generate_aws_account(
            user=self.user, name=faker.Faker().bs())
        self.account_plain = account_helper.generate_aws_account(
            user=self.other_user, name=faker.Faker().bs())

        # Images
        self.image_rhel = account_helper.generate_aws_image(rhel_detected=True)
        self.image_ocp = account_helper.generate_aws_image(
            openshift_detected=True)
        self.image_plain = account_helper.generate_aws_image()

        # Instances
        self.a1_instance_rhel = account_helper.generate_aws_instance(
            self.account_mixed, image=self.image_rhel)
        self.a1_instance_oc = account_helper.generate_aws_instance(
            self.account_mixed, image=self.image_ocp)
        self.a1_instance_unknown = account_helper.generate_aws_instance(
            self.account_mixed, no_image=True)
        self.a2_instance_plain = account_helper.generate_aws_instance(
            self.account_plain, image=self.image_plain)

        # Generate activity for instances belonging to self.user
        self.powered_times = (
            (
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 5, 0, 0)
            ),
            (
                util_helper.utc_dt(2018, 5, 10, 0, 0, 0),
                None
            ),
        )
        account_helper.generate_aws_instance_events(
            self.a1_instance_rhel,
            self.powered_times,
            ec2_ami_id=self.image_rhel.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            self.a1_instance_oc,
            self.powered_times,
            ec2_ami_id=self.image_ocp.ec2_ami_id,
        )
        account_helper.generate_aws_instance_events(
            self.a1_instance_unknown,
            self.powered_times,
            no_image=True,
        )
        account_helper.generate_aws_instance_events(
            self.a2_instance_plain,
            self.powered_times,
            ec2_ami_id=self.image_plain.ec2_ami_id,
        )

        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

        self.start_inactive = util_helper.utc_dt(2018, 3, 1, 0, 0, 0)
        self.end_inactive = util_helper.utc_dt(2018, 4, 1, 0, 0, 0)

        self.now = datetime.datetime.now(tz=tz.tzutc())
        future_year = self.now.year + 2

        self.start_future = util_helper.utc_dt(future_year, 1, 1, 0, 0, 0)
        self.end_future = util_helper.utc_dt(future_year, 2, 1, 0, 0, 0)

        self.factory = APIRequestFactory()
        account_helper.generate_aws_ec2_definitions()

    def get_report_response(self, as_user, start, end, account_id,
                            user_id=None):
        """
        Get the image activity overview API response for the given inputs.

        Args:
            as_user (User): Django auth user performing the request
            start (datetime.datetime): Start time request arg
            end (datetime.datetime): End time request arg
            account_id (int): required account_id to filter against
            user_id (int): Optional user_id request arg

        Returns:
            Response for this request.

        """
        data = {
            'start': start,
            'end': end,
            'account_id': account_id,
        }
        if user_id:
            data['user_id'] = user_id

        client = APIClient()
        client.force_authenticate(user=as_user)
        response = client.get('/api/v1/report/images/', data, format='json')
        return response

    def assertNoImages(self, response):
        """Assert no images were found in the response."""
        self.assertEqual(200, response.status_code)
        self.assertEqual(0, len(response.data['images']))

    def assertRhel(self, image_data, detected=False, challenged=False):
        """Assert if the image data should indicate RHEL."""
        rhel = operator.xor(detected, challenged)
        self.assertEqual(rhel, image_data['rhel'])
        self.assertEqual(detected, image_data['rhel_detected'])
        self.assertEqual(challenged, image_data['rhel_challenged'])

    def assertOpenShift(self, image_data, detected=False, challenged=False):
        """Assert if the image data should indicate OpenShift."""
        openshift = operator.xor(detected, challenged)
        self.assertEqual(openshift, image_data['openshift'])
        self.assertEqual(detected, image_data['openshift_detected'])
        self.assertEqual(challenged, image_data['openshift_challenged'])

    def assertUser1MixedAccount(self, response):
        """Assert findings for activity in self.account_mixed."""
        self.assertEqual(200, response.status_code)
        images = response.data['images']
        self.assertEqual(2, len(images))

        rhel_image_data = next((image for image in images
                                if image['id'] == self.image_rhel.id))
        self.assertEqual(rhel_image_data['instances_seen'], 1)
        self.assertEqual(rhel_image_data['runtime_seconds'], HOURS_5)
        self.assertRhel(rhel_image_data, True)
        self.assertOpenShift(rhel_image_data)

        ocp_image_data = next((image for image in images
                               if image['id'] == self.image_ocp.id))
        self.assertEqual(ocp_image_data['instances_seen'], 1)
        self.assertEqual(ocp_image_data['runtime_seconds'], HOURS_5)
        self.assertRhel(ocp_image_data)
        self.assertOpenShift(ocp_image_data, True)

    def test_various_images_for_active_account(self):
        """Assert images found when images were active."""
        response = self.get_report_response(self.user, self.start,
                                            self.end,
                                            account_id=self.account_mixed.id)
        self.assertUser1MixedAccount(response)

    def test_various_images_for_active_account_via_superuser(self):
        """Assert superuser gets same data when impersonating a user."""
        response = self.get_report_response(self.super_user, self.start,
                                            self.end,
                                            account_id=self.account_mixed.id,
                                            user_id=self.user.id)
        self.assertUser1MixedAccount(response)

    def test_no_images_for_account_with_images_previously_active(self):
        """Assert no images when no images were active in the time."""
        response = self.get_report_response(self.user, self.start_inactive,
                                            self.end_inactive,
                                            account_id=self.account_mixed.id)
        self.assertNoImages(response)

    @patch.object(views.serializers.misc, 'datetime')
    def test_future_seconds_truncated_for_unending_activity(self, mock_dt):
        """Assert we stop counting up runtime later than "now"."""
        delta_hours_5 = datetime.timedelta(seconds=HOURS_5)
        now = self.powered_times[1][0] + delta_hours_5
        near_future = now + delta_hours_5
        mock_dt.datetime.now.return_value = now
        response = self.get_report_response(self.user, self.start_inactive,
                                            near_future,
                                            account_id=self.account_mixed.id)
        self.assertUser1MixedAccount(response)

    def test_no_images_for_account_with_no_relevant_images(self):
        """Assert no images when no images were active in the account."""
        response = self.get_report_response(self.user, self.start, self.end,
                                            account_id=self.account_none.id)
        self.assertNoImages(response)
