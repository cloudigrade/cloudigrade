"""Collection of tests for MachineImageViewSet."""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from api.clouds.aws.models import AwsMachineImage
from api.models import MachineImage
from api.tests import helper as api_helper
from api.viewsets import MachineImageViewSet
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

        # Accounts for the users
        self.account_user1_aws1 = api_helper.generate_cloud_account_aws(user=self.user1)
        self.account_user1_aws2 = api_helper.generate_cloud_account_aws(user=self.user1)
        self.account_user1_azure1 = api_helper.generate_cloud_account_azure(
            user=self.user1
        )
        self.account_user2_aws1 = api_helper.generate_cloud_account_aws(user=self.user2)
        self.account_user2_aws2 = api_helper.generate_cloud_account_aws(user=self.user2)

        # Images with various contents
        self.image_aws_plain = api_helper.generate_image_aws()
        self.image_aws_windows = api_helper.generate_image_aws(is_windows=True)
        self.image_aws_rhel = api_helper.generate_image_aws(rhel_detected=True)
        self.image_aws_ocp = api_helper.generate_image_aws(
            openshift_detected=True, architecture="arm64"
        )
        self.image_aws_rhel_ocp = api_helper.generate_image_aws(
            rhel_detected=True, openshift_detected=True, status=MachineImage.UNAVAILABLE
        )
        self.image_aws_inspected = api_helper.generate_image_aws(
            status=MachineImage.INSPECTED
        )
        self.image_aws_broken = api_helper.generate_image_aws(
            missing_content_object=True
        )
        self.image_azure_plain = api_helper.generate_image_azure()
        self.image_azure_broken = api_helper.generate_image_aws(
            missing_content_object=True
        )

        # Instances for the accounts
        self.instance_user1_aws1 = api_helper.generate_instance_aws(
            cloud_account=self.account_user1_aws1, image=self.image_aws_plain
        )
        self.instance_user1_aws2_1 = api_helper.generate_instance_aws(
            cloud_account=self.account_user1_aws2, image=self.image_aws_rhel
        )
        self.instance_user1_aws2_2 = api_helper.generate_instance_aws(
            cloud_account=self.account_user1_aws2, image=self.image_aws_broken
        )
        self.instance_user1_azure1 = api_helper.generate_instance_azure(
            cloud_account=self.account_user1_azure1, image=self.image_azure_broken
        )
        self.instance_user2_aws1 = api_helper.generate_instance_aws(
            cloud_account=self.account_user2_aws1, image=self.image_aws_ocp
        )
        self.instance_user2_aws2 = api_helper.generate_instance_aws(
            cloud_account=self.account_user2_aws2, image=self.image_aws_rhel_ocp
        )

        # Some initial event activity spread across the accounts
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
            ),
        )
        instance_images = (
            (self.instance_user1_aws1, self.image_aws_plain),
            (self.instance_user1_aws2_1, self.image_aws_rhel),
            (self.instance_user1_aws2_2, self.image_aws_broken),
            (self.instance_user1_azure1, self.image_azure_broken),
            (self.instance_user2_aws1, self.image_aws_ocp),
            (self.instance_user2_aws2, self.image_aws_rhel_ocp),
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
            image (MachineImage): which image seen in the events.

        Returns:
            list[InstanceEvent]: The list of events

        """
        if image.content_object is None:
            events = []
        else:
            events = api_helper.generate_instance_events(
                instance,
                powered_times,
                image.content_object.ec2_ami_id,
            )
        return events

    def assertResponseHasImageData(self, response, image):
        """Assert the response has data matching the image object."""
        self.assertEqual(response.data["image_id"], image.id)
        self.assertEqual(
            Decimal(response.data["content_object"]["owner_aws_account_id"]),
            Decimal(image.content_object.owner_aws_account_id),
        )
        self.assertEqual(response.data["inspection_json"], image.inspection_json)
        self.assertEqual(response.data["name"], image.name)
        self.assertEqual(response.data["status"], image.status)
        self.assertEqual(response.data["rhel"], image.rhel)
        self.assertEqual(
            response.data["rhel_detected_by_tag"], image.rhel_detected_by_tag
        )
        self.assertEqual(response.data["openshift"], image.openshift)
        self.assertEqual(response.data["openshift_detected"], image.openshift_detected)

        if isinstance(image, AwsMachineImage):
            self.assertEqual(
                response.data["content_object"]["ec2_ami_id"], image.ec2_ami_id
            )
            self.assertEqual(
                response.data["is_encrypted"], image.machine_image.is_encrypted
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
        request = self.factory.get("/images/")
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={"get": "retrieve"})
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
        request = self.factory.put("/images/", data)
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={"put": "update"})
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
        request = self.factory.patch("/images/", data)
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={"patch": "partial_update"})
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
        request = self.factory.get("/images/", data)
        force_authenticate(request, user=user)
        view = MachineImageViewSet.as_view(actions={"get": "list"})
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
        image_ids = set([image["image_id"] for image in response.data["data"]])
        return image_ids

    def test_list_images_as_user1(self):
        """Assert that a user sees only its images relevant to its events."""
        expected_images = {
            self.image_aws_plain.id,
            self.image_aws_rhel.id,
            self.image_aws_broken.id,
            self.image_azure_broken.id,
        }
        response = self.get_image_list_response(self.user1)
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_with_architecture_filter(self):
        """Assert that a user sees images filtered by architecture."""
        expected_images = {
            self.image_aws_ocp.id,
        }
        response = self.get_image_list_response(self.user2, {"architecture": "arm64"})
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_list_images_with_status_filter(self):
        """Assert that a user sees images filtered by status."""
        expected_images = {
            self.image_aws_rhel_ocp.id,
        }
        response = self.get_image_list_response(
            self.user2, {"status": MachineImage.UNAVAILABLE}
        )
        actual_images = self.get_image_ids_from_list_response(response)
        self.assertEqual(expected_images, actual_images)

    def test_get_image_used_by_user_returns_ok(self):
        """Assert that user1 can get one of its own images."""
        user = self.user1
        images = [self.image_aws_plain, self.image_aws_rhel]  # Images used by user1.

        for image in images:
            response = self.get_image_get_response(user, image.id)
            self.assertEqual(response.status_code, 200)
            self.assertResponseHasImageData(response, image)

    def test_get_image_not_used_by_user_returns_404(self):
        """Assert that user2 cannot get an image it hasn't used."""
        user = self.user2
        image = self.image_aws_plain  # Image used by user1, NOT user2.

        response = self.get_image_get_response(user, image.id)
        self.assertEqual(response.status_code, 404)

    def test_marking_images_as_windows_tags_them_as_windows(self):
        """Assert that a windows image has an appropriate property."""
        image = self.image_aws_windows
        self.assertEqual(image.content_object.platform, image.content_object.WINDOWS)
