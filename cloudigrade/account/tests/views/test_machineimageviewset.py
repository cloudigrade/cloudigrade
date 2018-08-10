"""Collection of tests for MachineImageViewSet."""
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from account.models import (AwsMachineImage)
from account.tests import helper as account_helper
from account.views import (MachineImageViewSet)
from util.tests import helper as util_helper


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
        self.account5 = \
            account_helper.generate_aws_account(user=self.superuser)
        self.machine_image1 = \
            account_helper.generate_aws_image(account=self.account1,
                                              is_rhel=True)
        self.machine_image2 = \
            account_helper.generate_aws_image(account=self.account2,
                                              is_openshift=True)
        self.machine_image3 = \
            account_helper.generate_aws_image(account=self.account3,
                                              is_rhel=True,
                                              is_openshift=True)
        self.machine_image4 = \
            account_helper.generate_aws_image(account=self.account4,
                                              is_windows=True)
        self.machine_image5 = \
            account_helper.generate_aws_image(account=self.account5,
                                              is_rhel=True)
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
            self.machine_image4.id,
            self.machine_image5.id
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
        self.assertEqual(image.platform, image.WINDOWS)

    def test_user1_challenge_non_rhel_returns_ok(self):
        """Assert that user can challenge RHEL image as non RHEL."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.machine_image1.id,
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
                                               self.machine_image1.id,
                                               data1)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])

        response = self.get_image_put_response(self.user1,
                                               self.machine_image1.id,
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
                                                 self.machine_image2.id,
                                                 data)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertTrue(response.data['rhel'])

    def test_user1_challenge_non_ocp_returns_ok(self):
        """Assert that user can challenge OCP image as non OCP."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'openshift_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.machine_image2.id,
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
                                                 self.machine_image1.id,
                                                 data)
        self.assertTrue(response.data['openshift_challenged'])
        self.assertTrue(response.data['openshift'])

    def test_user1_challenge_user2_returns_404(self):
        """Assert that normal user can not challenge another users image."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.user1,
                                                 self.machine_image3.id,
                                                 data)
        self.assertEqual(response.status_code, 404)

    def test_super_challenge_user1_returns_403(self):
        """Assert that a superuser can not challenge another users image."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.superuser,
                                                 self.machine_image1.id,
                                                 data)
        self.assertEqual(response.status_code, 403)

        response = self.get_image_get_response(self.user1,
                                               self.machine_image1.id)
        self.assertFalse(response.data['rhel_challenged'])
        self.assertTrue(response.data['rhel'])

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
                                                 self.machine_image3.id,
                                                 data1)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])
        self.assertFalse(response.data['openshift_challenged'])
        self.assertTrue(response.data['openshift'])

        response = self.get_image_patch_response(self.user2,
                                                 self.machine_image3.id,
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
                                                 self.machine_image3.id,
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
                                                 self.machine_image1.id,
                                                 data1)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])

        response = self.get_image_patch_response(self.user1,
                                                 self.machine_image1.id,
                                                 data2)
        self.assertFalse(response.data['rhel_challenged'])
        self.assertTrue(response.data['rhel'])

    def test_superuser_can_challenge_own_account_returns_ok(self):
        """Assert that superuser can challenge own RHEL image as non RHEL."""
        data = {
            'resourcetype': 'AwsMachineImage',
            'rhel_challenged': True
        }

        response = self.get_image_patch_response(self.superuser,
                                                 self.machine_image5.id,
                                                 data)
        self.assertTrue(response.data['rhel_challenged'])
        self.assertFalse(response.data['rhel'])
