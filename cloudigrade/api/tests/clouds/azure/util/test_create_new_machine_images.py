"""Collection of tests for api.cloud.azure.util.create_new_machine_images."""
import faker
from django.test import TestCase

from api.clouds.azure import util
from api.clouds.azure.models import AzureMachineImage
from api.models import MachineImage
from util import OPENSHIFT_TAG, RHEL_TAG
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateAzureNewMachineImages(TestCase):
    """Test cases for api.cloud.azure.util.create_new_machine_images."""

    def setUp(self):
        """Set up shared variables."""
        self.user = util_helper.generate_test_user()
        self.subscription_id = _faker.uuid4()
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.source_id = _faker.pyint()

    def test_create_new_machine_images(self):
        """Tests creation of two machine images."""
        vm1 = util_helper.generate_vm_data()
        vm2 = util_helper.generate_vm_data()
        new_skus = util.create_new_machine_images([vm1, vm2])
        self.assertSetEqual(set(new_skus), {vm1["image_sku"], vm2["image_sku"]})
        self.assertTrue(AzureMachineImage.objects.count() == 2)
        self.assertTrue(
            AzureMachineImage.objects.filter(resource_id=vm1["image_sku"]).exists()
        )
        self.assertTrue(
            AzureMachineImage.objects.filter(resource_id=vm2["image_sku"]).exists()
        )

    def test_create_new_machine_images_rhel_detected(self):
        """Tests creation of a machine image that is tagged as RHEL."""
        vm1 = util_helper.generate_vm_data(tags={RHEL_TAG: 1})
        new_skus = util.create_new_machine_images([vm1])
        self.assertSetEqual(set(new_skus), {vm1["image_sku"]})
        self.assertTrue(AzureMachineImage.objects.count() == 1)
        self.assertTrue(
            AzureMachineImage.objects.filter(resource_id=vm1["image_sku"]).exists()
        )
        self.assertTrue(MachineImage.objects.count() == 1)
        self.assertTrue(
            MachineImage.objects.filter(
                name=vm1["image_sku"],
                rhel_detected_by_tag=True,
                openshift_detected=False,
            ).exists()
        )

    def test_create_new_machine_images_openshift_detected(self):
        """Tests creation of a machine image that is tagged as openshift."""
        vm1 = util_helper.generate_vm_data(tags={OPENSHIFT_TAG: 1})
        new_skus = util.create_new_machine_images([vm1])
        self.assertSetEqual(set(new_skus), {vm1["image_sku"]})
        self.assertTrue(AzureMachineImage.objects.count() == 1)
        self.assertTrue(
            AzureMachineImage.objects.filter(resource_id=vm1["image_sku"]).exists()
        )
        self.assertTrue(MachineImage.objects.count() == 1)
        self.assertTrue(
            MachineImage.objects.filter(
                name=vm1["image_sku"],
                rhel_detected_by_tag=False,
                openshift_detected=True,
            ).exists()
        )

    def test_create_new_machine_images_rhel_and_openshift_detected(self):
        """Tests creation of a machine image that is tagged as rhel and openshift."""
        vm1 = util_helper.generate_vm_data(tags={OPENSHIFT_TAG: 1, RHEL_TAG: 1})
        new_skus = util.create_new_machine_images([vm1])
        self.assertSetEqual(set(new_skus), {vm1["image_sku"]})
        self.assertTrue(AzureMachineImage.objects.count() == 1)
        self.assertTrue(
            AzureMachineImage.objects.filter(resource_id=vm1["image_sku"]).exists()
        )
        self.assertTrue(MachineImage.objects.count() == 1)
        self.assertTrue(
            MachineImage.objects.filter(
                name=vm1["image_sku"],
                rhel_detected_by_tag=True,
                openshift_detected=True,
            ).exists()
        )
