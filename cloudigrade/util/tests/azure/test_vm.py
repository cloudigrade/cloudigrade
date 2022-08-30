"""Collection of tests for ``util.azure.vm`` module."""
import json
from unittest.mock import Mock, patch

import faker
from azure.core.exceptions import ClientAuthenticationError
from django.test import TestCase


from util.azure import vm as vm_util

log_prefix = "util.azure.vm"

_faker = faker.Faker()


class GenericObject(object):
    """Definition of a Generic Object used in simulating Azure SDK API objects."""

    pass


class UtilAzureVmTest(TestCase):
    """Azure Vm utility functions test case."""

    def setUp(self):
        """Set up some common globals for the vm tests."""
        self.name = _faker.slug()
        self.type = "Microsoft.Compute/virtualMachines"
        self.resourceGroup = _faker.slug()
        self.subscription = _faker.uuid4()
        self.full_id = (
            f"/subscriptions/{self.subscription}"
            f"/resourceGroups/{self.resourceGroup}"
            f"/providers/Microsoft.Compute/virtualMachines/{self.name}"
        )
        self.vm_id = _faker.uuid4()
        self.location = "eastus"
        self.vm_arch = "x64"
        self.vm_size = "Standard_D2s_v3"

        self.vm = GenericObject()
        self.vm.id = self.full_id
        self.vm.vm_id = self.vm_id
        self.vm.location = self.location
        self.vm.name = self.name
        self.vm.type = self.type
        self.vm.plan = None
        self.vm.instance_view = Mock()
        self.vm.hardware_profile = Mock()
        self.vm.hardware_profile.vm_size = self.vm_size
        self.vm.storage_profile = Mock()
        self.vm.storage_profile.os_disk = Mock()
        self.sku_image_properties = Mock()
        self.sku_image_properties.additional_properties = {
            "properties": {
                "hyperVGeneration": "V2",
                "architecture": self.vm_arch,
            }
        }

    @patch("azure.mgmt.compute.ComputeManagementClient")
    def test_get_vms_for_subscription(self, mock_cmc):
        """Tests the get_vms_for_subscription helper method."""
        mock_cmclient = Mock()
        mock_cmc.return_value = mock_cmclient
        mock_cmclient.side_effect = ClientAuthenticationError

        with self.assertLogs(log_prefix, level="ERROR") as logging_watcher:
            vms = vm_util.get_vms_for_subscription(self.subscription)
            self.assertIn(
                f"Could not discover vms for subscription {self.subscription}, "
                "Failed to authenticate a new client.",
                logging_watcher.output[0],
            )
        self.assertEqual(vms, [])

    def test_vm_info(self):
        """Tests that vm_info returns the expected dictionary."""
        cm_client = Mock()
        sku = _faker.slug()
        image_data = {"offer": "RHEL", "sku": sku}
        image_reference = GenericObject()
        image_reference.offer = image_data["offer"]
        image_reference.sku = sku
        image_properties = {}
        image_properties[sku] = self.sku_image_properties
        status = Mock()
        status.code = "PowerState/running"
        self.vm.storage_profile.image_reference = image_reference
        self.vm.instance_view.statuses = [status]
        self.vm.storage_profile.image_reference = image_reference
        self.vm.storage_profile.os_disk.encryption_settings = {"enabled": True}
        vm_info = vm_util.vm_info(cm_client, image_properties, self.vm, None)
        vm_info_contains = {
            "id": self.vm.id,
            "vm_id": self.vm.vm_id,
            "name": self.vm.name,
            "type": self.vm.type,
            "image_sku": sku,
            "region": self.vm.location,
            "azure_marketplace_image": False,
            "resourceGroup": vm_util.resource_group(self.vm),
            "running": True,
            "is_encrypted": True,
            "architecture": self.vm_arch,
            "vm_size": self.vm_size,
            "inspection_json": json.dumps({"image_reference": image_data}),
        }
        self.assertDictContainsSubset(vm_info_contains, vm_info)

    def test_find_vm(self):
        """Tests that find_vm returns the correct vm from the list of vms."""
        vm1 = GenericObject()
        vm1.id = _faker.uuid4()
        vm2 = GenericObject()
        vm2.id = _faker.uuid4()
        self.assertEqual(vm_util.find_vm([vm1, vm2], vm2.id), vm2)

    def test_find_vm_missing(self):
        """Tests that find_vm returns None if the vm id is missing."""
        vm1 = GenericObject()
        vm1.id = _faker.uuid4()
        self.assertIsNone(vm_util.find_vm([vm1], _faker.uuid4()))

    def test_get_image_properties_cached(self):
        """Test that get_image_properties returns the cached properties if there."""
        sku = _faker.slug()
        image_reference = Mock()
        image_reference.sku = sku
        self.vm.storage_profile.image_reference = image_reference
        image_properties = {}
        image_properties[sku] = self.sku_image_properties
        self.assertEqual(
            vm_util.get_image_properties(None, image_properties, self.vm),
            self.sku_image_properties,
        )

    def test_get_image_properties(self):
        """Test that get_image_properties fetches the properties."""
        cm_client = Mock()
        sku = _faker.slug()
        publisher = "RedHat"
        image_reference = Mock()
        image_reference.publisher = publisher
        image_reference.sku = sku
        self.vm.storage_profile.image_reference = image_reference
        cm_client.virtual_machine_images = Mock()
        cm_client.virtual_machine_images.list.return_value = [self.sku_image_properties]
        image_properties = {}
        new_image_properties = vm_util.get_image_properties(
            cm_client, image_properties, self.vm
        )
        self.assertEqual(new_image_properties, self.sku_image_properties)
        self.assertEqual(image_properties[sku], new_image_properties)

    def test_get_image_properties_new(self):
        """Test that get_image_properties fetches the properties if not cached."""

    def test_architecture(self):
        """Return the architecture for the image properties specified."""
        image_properties = GenericObject()
        image_properties.additional_properties = {
            "properties": {"architecture": self.vm_arch}
        }
        self.assertEqual(vm_util.architecture(image_properties), self.vm_arch)

    def test_is_markerplace_image_true(self):
        """Returns True if the vm image is from the marketplace."""
        self.vm.plan = "MarketPlace Plan"
        self.assertTrue(vm_util.is_marketplace_image(self.vm))

    def test_is_markerplace_image_false(self):
        """Returns False if the vm image is not from the marketplace."""
        self.vm.plan = None
        self.assertFalse(vm_util.is_marketplace_image(self.vm))

    def test_inspection_json(self):
        """Returns the inspection json that includes the image reference."""
        image_data = {"offer": "RHEL", "sku": "82gen2"}
        image_reference = GenericObject()
        image_reference.offer = image_data["offer"]
        image_reference.sku = image_data["sku"]
        self.vm.storage_profile.image_reference = image_reference
        self.assertEqual(
            vm_util.inspection_json(self.vm),
            json.dumps({"image_reference": image_data}),
        )

    def test_is_running_true(self):
        """Return true if the vm specified is running."""
        status = Mock()
        status.code = "PowerState/running"
        self.vm.instance_view.statuses = [status]
        self.assertTrue(vm_util.is_running(self.vm))

    def test_is_running_false(self):
        """Return false if the vm specified is not running."""
        self.vm.instance_view.statuses = []
        self.assertFalse(vm_util.is_running(self.vm))

    def test_is_encrypted_true(self):
        """Tests that we return True if the vm specified is encrypted."""
        self.vm.storage_profile.os_disk.encryption_settings = {"enabled": True}
        self.assertTrue(vm_util.is_encrypted(self.vm))

    def test_is_encrypted_false(self):
        """Tests that we return False if the vm specified is not encrypted."""
        self.vm.storage_profile.os_disk.encryption_settings = None
        self.assertFalse(vm_util.is_encrypted(self.vm))

    def test_resource_group(self):
        """Tests that we propely parse the resourceGroup out of an object id."""
        self.assertEqual(vm_util.resource_group(self.vm), self.resourceGroup)
