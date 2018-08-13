"""Collection of tests for MachineImageViewSet."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from account.models import AwsMachineImage
from account.tests import helper as account_helper
from account.views import MachineImageViewSet
from util.tests import helper as util_helper


class MachineImageViewSetTest(TestCase):
    """MachineImageViewSet test case."""

    def setUp(self):
        """
        Set up a bunch of test data.

        This gets very noisy very quickly because we need users who have
        accounts that have instances that have events that used various image
        types.
        """
        # Users
        self.user1 = util_helper.generate_test_user()
        self.user2 = util_helper.generate_test_user()
        self.superuser = util_helper.generate_test_user(is_superuser=True)

        # Accounts for the users
        self.account_u1_1 = account_helper.generate_aws_account(
            user=self.user1)
        self.account_u1_2 = account_helper.generate_aws_account(
            user=self.user1)
        self.account_u2_1 = account_helper.generate_aws_account(
            user=self.user2)
        self.account_u2_2 = account_helper.generate_aws_account(
            user=self.user2)
        self.account_su = account_helper.generate_aws_account(
            user=self.superuser)

        # Instances for the accounts
        self.instance_u1_1 = account_helper.generate_aws_instance(
            account=self.account_u1_1)
        self.instance_u1_2 = account_helper.generate_aws_instance(
            account=self.account_u1_2)
        self.instance_u2_1 = account_helper.generate_aws_instance(
            account=self.account_u2_1)
        self.instance_u2_2 = account_helper.generate_aws_instance(
            account=self.account_u2_2)
        self.instance_su = account_helper.generate_aws_instance(
            account=self.account_su)

        # Images wih various contents
        self.image_plain = account_helper.generate_aws_image()
        self.image_windows = account_helper.generate_aws_image(is_windows=True)
        self.image_rhel = account_helper.generate_aws_image(rhel_detected=True)
        self.image_ocp = account_helper.generate_aws_image(
            openshift_detected=True)
        self.image_rhel_ocp = account_helper.generate_aws_image(
            rhel_detected=True, openshift_detected=True)

        # Some initial event activity spread across the accounts
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0)
            ),
        )
        instance_images = (
            (self.instance_u1_1, self.image_plain),
            (self.instance_u1_2, self.image_rhel),
            (self.instance_u2_1, self.image_ocp),
            (self.instance_u2_2, self.image_rhel_ocp),
            (self.instance_su, self.image_windows),
        )
        for instance, image in instance_images:
            self.generate_events(powered_times, instance, image)

        self.factory = APIRequestFactory()

    def generate_events(self, powered_times, instance, image):
        """
        Generate events saved to the DB and returned.

        Args:
            powered_times (list[tuple]): Time periods instance is powered on.
            instance (Instance): which instance has the events.
            image (AwsMachineImage): which image seen in the events.

        Returns:
            list[InstanceEvent]: The list of events

        """
        events = account_helper.generate_aws_instance_events(
            instance, powered_times, image.ec2_ami_id,
        )
        return events

    def assertResponseHasImageData(self, response, image):
        """Assert the response has data matching the image object."""
        self.assertEqual(
            response.data['id'], image.id
        )
        self.assertEqual(
            Decimal(response.data['owner_aws_account_id']),
            Decimal(image.owner_aws_account_id)
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

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.get('/image/')
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={'get': 'retrieve'})
        response = view(request, pk=image_id)
        return response

    def get_image_put_response(self, user, image_id, data):
        """
        Generate a response for a put-update on the MachineImageViewSet.

        Args:
            user (User): Django auth user performing the request.
            image_id (int): ID of the image to update.
            data (dict): Data to update the image with.

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.put('/image/', data)
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={'put': 'update'})
        response = view(request, pk=image_id)
        return response

    def get_image_patch_response(self, user, image_id, data):
        """
        Generate a response for a patch-update on the MachineImageViewSet.

        Args:
            user (User): Django auth user performing the request.
            image_id (int): ID of the image to update.
            data (dict): Data to update the image with.

        Returns:
            Response: the generated response for this request

        """
        request = self.factory.patch('/image/', data)
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={'patch': 'partial_update'})
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
        """Assert that a user sees only its images relevant to its events."""
        expected_images = {
            self.image_plain.id,
            self.image_rhel.id,
        }
        response = self.get_image_list_response(self.user1)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_as_superuser(self):
        """Assert that the superuser sees all images regardless of owner."""
        expected_images = {
            self.image_plain.id,
            self.image_windows.id,
            self.image_rhel.id,
            self.image_ocp.id,
            self.image_rhel_ocp.id
        }
        response = self.get_image_list_response(self.superuser)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_as_superuser_with_filter(self):
        """Assert that the superuser sees images filtered by user_id."""
        expected_images = {
            self.image_ocp.id,
            self.image_rhel_ocp.id
        }
        params = {'user_id': self.user2.id}
        response = self.get_image_list_response(self.superuser, params)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_get_image_used_by_user_returns_ok(self):
        """Assert that user1 can get one of its own images."""
        user = self.user1
        image = self.image_plain  # Image used by user1.

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasImageData(response, image)

    def test_get_image_not_used_by_user_returns_404(self):
        """Assert that user2 cannot get an image it hasn't used."""
        user = self.user2
        image = self.image_plain  # Image used by user1, NOT user2.

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 404)

    def test_get_image_used_by_user_as_superuser_returns_ok(self):
        """Assert that superuser can get an image used by another user."""
        user = self.superuser
        # Image used by user1, NOT superuser.
        image = self.image_plain

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 200)
        self.assertResponseHasImageData(response, image)

    def test_list_images_as_superuser_with_bad_filter(self):
        """Assert that the list images returns 400 with bad user_id."""
        params = {'user_id': 'not_an_int'}
        response = self.get_image_list_response(self.superuser, params)
        self.assertEqual(response.status_code, 400)

    def test_marking_images_as_windows_tags_them_as_windows(self):
        """Assert that a windows image has an appropriate property."""
        image = self.image_windows
        self.assertEqual(image.platform, image.WINDOWS)

    def test_user1_challenge_non_rhel_returns_ok(self):
        """Assert that user can challenge RHEL image as non RHEL."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.image_rhel.id,
                                                 data)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])

    def test_user1_challenge_using_put_returns_ok(self):
        """Assert that user can challenge RHEL image as non RHEL."""
        data1 = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }
        data2 = {
            'resourcetype': 'AwsMachineImage',
            'openshift_challenged': True
        }

        response = self.get_image_put_response(self.user1,
                                               self.image_rhel.id,
                                               data1)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])

        response = self.get_image_put_response(self.user1,
                                               self.image_rhel.id,
                                               data2)
        self.assertTrue(response.data['openshift_challenged'])
        self.assertTrue(response.data['openshift'])
        self.assertFalse(response.data['rhel_challenged'])
        self.assertTrue(response.data['rhel'])

    def test_user1_challenge_rhel_returns_ok(self):
        """Assert that user can challenge non RHEL image as RHEL."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.image_plain.id,
                                                 data)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertTrue(response.data['rhel'])

    def test_user2_challenge_non_ocp_returns_ok(self):
        """Assert that user can challenge OCP image as non OCP."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'openshift_challenged': True
        }

        response = self.get_image_patch_response(self.user2,
                                                 self.image_ocp.id,
                                                 data)
        self.assertTrue(response.data['openshift_challenged'])
        self.assertFalse(response.data['openshift'])

    def test_user1_challenge_ocp_returns_ok(self):
        """Assert that user can challenge non OCP image as OCP."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'openshift_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.image_plain.id,
                                                 data)
        self.assertTrue(response.data['openshift_challenged'])
        self.assertTrue(response.data['openshift'])

    def test_user1_challenge_user2_returns_404(self):
        """Assert that user can not challenge image it hasn't used."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.image_ocp.id,
                                                 data)
        self.assertEqual(response.status_code, 404)

    def test_user2_challenge_both_individually_returns_ok(self):
        """Assert that user can challenge RHEL and OCP individually."""
        data1 = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }
        data2 = {
            'resourcetype': 'AwsMachineImage',
            'openshift_challenged': True
        }

        response = self.get_image_patch_response(self.user2,
                                                 self.image_rhel_ocp.id,
                                                 data1)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])
        self.assertFalse(response.data['openshift_challenged'])
        self.assertTrue(response.data['openshift'])

        response = self.get_image_patch_response(self.user2,
                                                 self.image_rhel_ocp.id,
                                                 data2)
        self.assertTrue(response.data['openshift_challenged'])
        self.assertFalse(response.data['openshift'])
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])

    def test_user2_challenge_both_together_returns_ok(self):
        """Assert that user can challenge RHEL and OCP at the same time."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True,
            'openshift_challenged': True
        }

        response = self.get_image_patch_response(self.user2,
                                                 self.image_rhel_ocp.id,
                                                 data)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])
        self.assertTrue(response.data['openshift_challenged'])
        self.assertFalse(response.data['openshift'])

    def test_user1_undo_challenge_returns_ok(self):
        """Assert that user can redact a challenge RHEL."""
        data1 = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }
        data2 = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': False
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.image_rhel.id,
                                                 data1)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])

        response = self.get_image_patch_response(self.user1,
                                                 self.image_rhel.id,
                                                 data2)
        self.assertFalse(response.data['rhel_challenged'])
        self.assertTrue(response.data['rhel'])

    def test_superuser_can_challenge_image_returns_ok(self):
        """Assert that superuser can challenge image it hasn't used."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.superuser,
                                                 self.image_rhel.id,
                                                 data)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])
