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

    def __init__(self, **kwargs):
        """Initialize a GenericObject with the attributes specified."""
        for key, value in kwargs.items():
            setattr(self, key, value)


class UtilAzureVmTest(TestCase):
    """Azure Vm utility functions test case."""

    def setUp(self):
        """Set up some common globals for the vm tests."""
        self.name = _faker.slug()
        self.vm_type = "Microsoft.Compute/virtualMachines"
        self.vmss_type = "Microsoft.Compute/virtualMachinesScaleSets"
        self.resourceGroup = _faker.slug()
        self.subscription = _faker.uuid4()
        self.full_id = (
            f"/subscriptions/{self.subscription}"
            f"/resourceGroups/{self.resourceGroup}"
            f"/providers/{self.vm_type}/{self.name}"
        )
        self.vm_id = _faker.uuid4()
        self.location = "eastus"
        self.vm_arch = "x64"
        self.vm_size = "Standard_D2s_v3"

        self.vm = GenericObject(
            id=self.vm_full_id(
                subscription=self.subscription,
                resourceGroup=self.resourceGroup,
                name=self.name,
            ),
            vm_id=self.vm_id,
            location=self.location,
            name=self.name,
            type=self.vm_type,
            plan=None,
            instance_view=Mock(),
            hardware_profile=Mock(vm_size=self.vm_size),
            storage_profile=Mock(os_disk=Mock()),
        )
        self.sku_image_properties = Mock(
            additional_properties={
                "properties": {
                    "hyperVGeneration": "V2",
                    "architecture": self.vm_arch,
                }
            }
        )

    def vm_full_id(
        self, subscription=None, resourceGroup=None, name=None, is_vmss_vm=False
    ):
        """Return the full id of a VirtualMachine."""
        return (
            f"/subscriptions/{subscription or _faker.uuid4()}"
            f"/resourceGroups/{resourceGroup or _faker.slug()}"
            "/providers/Microsoft.Compute/"
            f"{self.get_vm_type(is_vmss_vm)}/{name or _faker.slug()}"
        )

    def get_vm_type(self, is_vmss_vm=False):
        """Return the vm_type for regular or scale set vm."""
        if is_vmss_vm:
            return self.vmss_type
        else:
            return self.vm_type

    def vmss_obj(self, subscription=None, resourceGroup=None, name=None):
        """Return a VM Scale Set object."""
        vmss_subscription = subscription or _faker.uuid4()
        vmss_name = name or _faker.slug()
        vmss_resourceGroup = resourceGroup or _faker.slug()
        return GenericObject(
            name=vmss_name,
            id=(
                f"/subscriptions/{vmss_subscription}"
                f"/resourceGroups/{vmss_resourceGroup}"
                "/providers/Microsoft.Compute/"
                f"virtualMachineScaleSets/{vmss_name}"
            ),
        )

    def instance_view_obj(self, is_running=True):
        """Return a mocked instance_view object."""
        instance_view = Mock()
        if is_running:
            status = Mock(code="PowerState/running")
        else:
            status = Mock(code="PowerState/stopped")
        instance_view.statuses = [status]
        return instance_view

    def image_properties_obj(self):
        """Return an image_properties object for an x64 image."""
        return Mock(
            additional_properties={
                "properties": {
                    "hyperVGeneration": "V2",
                    "architecture": "x64",
                    "replicaType": "Managed",
                    "replicaCount": 10,
                }
            }
        )

    def image_reference_obj(self, sku=None):
        """Return an image reference for a RHEL image."""
        return GenericObject(
            additional_properties={},
            publisher="RedHat",
            offer="RHEL",
            sku=sku or "82gen2",
            version="latest",
            exact_version="8.2.2022031402",
        )

    def vm_obj(self, name=None, is_vmss_vm=False, is_running=True):
        """Return a mocked vm object."""
        name = name or self.name
        return GenericObject(
            id=self.vm_full_id(
                subscription=self.subscription,
                resourceGroup=self.resourceGroup,
                name=name,
                is_vmss_vm=is_vmss_vm,
            ),
            vm_id=self.vm_id,
            location=self.location,
            name=name,
            type=self.get_vm_type(is_vmss_vm),
            plan=None,
            instance_view=self.instance_view_obj(is_running=is_running),
            hardware_profile=Mock(vm_size=self.vm_size),
            storage_profile=Mock(
                os_disk=Mock(), image_reference=self.image_reference_obj()
            ),
        )

    @patch("util.azure.vm.ComputeManagementClient")
    def test_get_vms_for_subscription_success(self, mock_cmc):
        """Tests the get_vms_for_subscription success with regular and scale set vms."""
        mock_cmclient = Mock()
        mock_cmc.return_value = mock_cmclient

        vm1_name = _faker.slug()  # standalone vm 1
        vm2_name = _faker.slug()  # standalone vm 2
        vm3_name = _faker.slug()  # scale set vm 3
        vm_list = [
            self.vm_obj(name=vm1_name),
            self.vm_obj(name=vm2_name, is_running=False),
        ]
        vmss_list = [self.vmss_obj(subscription=self.subscription)]
        vmss_vms_list = [self.vm_obj(name=vm3_name, is_vmss_vm=True)]
        mock_cmclient.virtual_machine_images.list.return_value = [
            self.image_properties_obj()
        ]
        mock_cmclient.virtual_machines.list_all.return_value = vm_list
        mock_cmclient.virtual_machine_scale_sets.list_all.return_value = vmss_list
        mock_cmclient.virtual_machine_scale_set_vms.list.return_value = vmss_vms_list

        vms = vm_util.get_vms_for_subscription(self.subscription)
        self.assertEqual(vms[0]["type"], self.vm_type)
        self.assertEqual(vms[1]["type"], self.vm_type)
        self.assertEqual(vms[2]["type"], self.vmss_type)
        self.assertEqual(vms[0]["name"], vm1_name)
        self.assertEqual(vms[1]["name"], vm2_name)
        self.assertEqual(vms[2]["name"], vm3_name)

    @patch("util.azure.vm.ComputeManagementClient")
    def test_get_vms_for_subscription_failed_auth(self, mock_cmc):
        """Tests the get_vms_for_subscription with failed auth."""
        mock_cmclient = Mock()
        mock_cmc.return_value = mock_cmclient
        mock_cmclient.virtual_machines.list_all.side_effect = ClientAuthenticationError(
            "simulated auth error"
        )

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
        image_reference = GenericObject(offer=image_data["offer"], sku=sku)
        image_properties = {}
        image_properties[sku] = self.sku_image_properties
        status = Mock(code="PowerState/running")
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
        vm1 = GenericObject(id=_faker.uuid4())
        vm2 = GenericObject(id=_faker.uuid4())
        self.assertEqual(vm_util.find_vm([vm1, vm2], vm2.id), vm2)

    def test_find_vm_missing(self):
        """Tests that find_vm returns None if the vm id is missing."""
        vm1 = GenericObject(id=_faker.uuid4())
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
        image_properties = GenericObject(
            additional_properties={"properties": {"architecture": self.vm_arch}}
        )
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
        image_reference = GenericObject(
            offer=image_data["offer"], sku=image_data["sku"]
        )
        self.vm.storage_profile.image_reference = image_reference
        self.assertEqual(
            vm_util.inspection_json(self.vm),
            json.dumps({"image_reference": image_data}),
        )

    def test_is_running_true(self):
        """Return true if the vm specified is running."""
        status = Mock(code="PowerState/running")
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
