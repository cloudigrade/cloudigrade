"""Collection of tests for internal viewsets."""
import decimal

from django.test import TestCase

from api import models
from api.clouds.aws import models as aws_models
from api.models import User
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class InternalViewSetTest(TestCase):
    """Test internal viewsets."""

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
        self.user3 = util_helper.generate_test_user()

        # Accounts for the users
        self.account_u1_1 = api_helper.generate_cloud_account(user=self.user1)
        self.account_u1_2 = api_helper.generate_cloud_account(user=self.user1)
        self.account_u2_1 = api_helper.generate_cloud_account(user=self.user2)
        self.account_u2_2 = api_helper.generate_cloud_account(user=self.user2)

        # Images with various contents
        self.image_plain = api_helper.generate_image()
        self.image_windows = api_helper.generate_image(is_windows=True)
        self.image_rhel = api_helper.generate_image(rhel_detected=True)
        self.image_ocp = api_helper.generate_image(
            openshift_detected=True, architecture="arm64"
        )
        self.image_rhel_ocp = api_helper.generate_image(
            rhel_detected=True,
            openshift_detected=True,
            status=models.MachineImage.UNAVAILABLE,
        )
        self.inspected_image = api_helper.generate_image(
            status=models.MachineImage.INSPECTED
        )

        # Instances for the accounts
        self.instance_u1_1 = api_helper.generate_instance(
            cloud_account=self.account_u1_1, image=self.image_plain
        )
        self.instance_u1_2 = api_helper.generate_instance(
            cloud_account=self.account_u1_2, image=self.image_rhel
        )
        self.instance_u2_1 = api_helper.generate_instance(
            cloud_account=self.account_u2_1, image=self.image_ocp
        )
        self.instance_u2_2 = api_helper.generate_instance(
            cloud_account=self.account_u2_2, image=self.image_rhel_ocp
        )

        # Some initial event activity spread across the accounts
        powered_times = (
            (
                util_helper.utc_dt(2018, 1, 9, 0, 0, 0),
                util_helper.utc_dt(2018, 1, 10, 0, 0, 0),
            ),
        )
        instance_images = (
            (self.instance_u1_1, self.image_plain),
            (self.instance_u1_2, self.image_rhel),
            (self.instance_u2_1, self.image_ocp),
            (self.instance_u2_2, self.image_rhel_ocp),
        )
        self.events = []
        for instance, image in instance_images:
            self.events.extend(self.generate_events(powered_times, instance, image))

        self.client = api_helper.SandboxedRestClient(
            api_root="/internal/api/cloudigrade/v1"
        )
        self.client._force_authenticate(self.user3)

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
        events = api_helper.generate_instance_events(
            instance,
            powered_times,
            image.content_object.ec2_ami_id,
        )
        return events

    def test_list_users(self):
        """Assert that a user sees all User objects."""
        users = list(User.objects.all())
        expected_account_numbers = set(user.account_number for user in users)

        response = self.client.get_users()
        count = response.data["meta"]["count"]
        actual_account_numbers = set(
            item["account_number"] for item in response.data["data"]
        )

        self.assertGreater(count, 0)
        self.assertEqual(count, len(users))
        self.assertEqual(expected_account_numbers, actual_account_numbers)

    def test_list_cloudaccounts(self):
        """Assert that a user sees all CloudAccount objects."""
        cloudaccounts = list(models.CloudAccount.objects.all())
        expected_ids = set(account.id for account in cloudaccounts)

        response = self.client.get_cloudaccounts()
        actual_ids = set(item["id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(cloudaccounts))
        self.assertEqual(expected_ids, actual_ids)

    def test_list_instances(self):
        """Assert that a user sees all Instance objects."""
        instances = list(models.Instance.objects.all())
        expected_ids = set(instance.id for instance in instances)

        response = self.client.get_instances()
        actual_ids = set(item["id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(instances))
        self.assertEqual(expected_ids, actual_ids)

    def test_list_machineimages(self):
        """Assert that a user sees all MachineImage objects."""
        images = list(models.MachineImage.objects.all())
        expected_ids = set(image.id for image in images)

        response = self.client.get_machineimages()
        actual_ids = set(item["id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(images))
        self.assertEqual(expected_ids, actual_ids)

    def test_reinspect_machineimage(self):
        """Assert that a user can reinspect a MachineImage."""
        response = self.client.post_machineimages(
            noun_id=self.inspected_image.id,
            detail="reinspect",
            api_root="/internal/api/cloudigrade/v1",
        )
        self.inspected_image.refresh_from_db()
        self.assertEqual(models.MachineImage.PENDING, response.data["status"])
        self.assertEqual(models.MachineImage.PENDING, self.inspected_image.status)

    def test_list_awscloudaccounts(self):
        """Assert that a user sees all AwsCloudAccount objects."""
        accounts = list(aws_models.AwsCloudAccount.objects.all())
        expected_ids = set(account.aws_account_id for account in accounts)

        response = self.client.get_awscloudaccounts()
        actual_ids = set(
            decimal.Decimal(item["aws_account_id"]) for item in response.data["data"]
        )
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(accounts))
        self.assertEqual(expected_ids, actual_ids)

    def test_list_awsinstances(self):
        """Assert that a user sees all AwsInstance objects."""
        instances = list(aws_models.AwsInstance.objects.all())
        expected_ids = set(instance.ec2_instance_id for instance in instances)

        response = self.client.get_awsinstances()
        actual_ids = set(item["ec2_instance_id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(instances))
        self.assertEqual(expected_ids, actual_ids)

    def test_list_awsmachineimages(self):
        """Assert that a user sees all AwsMachineImage objects."""
        machineimages = list(aws_models.AwsMachineImage.objects.all())
        expected_ids = set(machineimage.ec2_ami_id for machineimage in machineimages)

        response = self.client.get_awsmachineimages()
        actual_ids = set(item["ec2_ami_id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(machineimages))
        self.assertEqual(expected_ids, actual_ids)

    def test_list_awsinstanceevents(self):
        """Assert that a user sees all AwsInstance objects."""
        events = list(aws_models.AwsInstanceEvent.objects.all())
        expected_ids = set(event.id for event in events)

        response = self.client.get_awsinstanceevents()
        actual_ids = set(item["id"] for item in response.data["data"])
        count = response.data["meta"]["count"]

        self.assertGreater(count, 0)
        self.assertEqual(count, len(events))
        self.assertEqual(expected_ids, actual_ids)
