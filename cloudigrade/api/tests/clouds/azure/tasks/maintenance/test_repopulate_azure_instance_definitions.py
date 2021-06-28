"""Collection of tests for api.tasks.cloudtrail.repopulate_azure_instance_mapping."""
import json
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import bitmath
import faker
from django.test import TestCase

from api.clouds.azure import tasks
from api.models import InstanceDefinition

_faker = faker.Faker()

# Token for this string since some of the paths in "patch" uses are very long.
_MAINTENANCE = "api.clouds.azure.tasks.maintenance"


class RepopulateAzureInstanceMappingTest(TestCase):
    """Celery task 'repopulate_azure_instance_mapping' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.standard_a5_definition = Mock()
        self.standard_a5_definition.name = "Standard_A5"
        self.standard_a5_definition.resource_type = "virtualMachines"
        vcpu_capability = Mock()
        vcpu_capability.name = "vCPUs"
        vcpu_capability.value = 0.75
        memory_capability = Mock()
        memory_capability.name = "MemoryGB"
        memory_capability.value = 14
        capabilities_list = [vcpu_capability, memory_capability]
        self.standard_a5_definition.capabilities = capabilities_list
        self.good_json = json.dumps(
            self.standard_a5_definition, default=lambda x: x.__dict__
        )
        self.good_14GB_to_MiB = int(bitmath.GB(14).to_MiB())

        self.bad_standard_a5_definition = Mock()
        self.bad_standard_a5_definition.name = "Standard_A5"
        self.bad_standard_a5_definition.resource_type = "virtualMachines"
        vcpu_capability = Mock()
        vcpu_capability.name = "vCPUs"
        vcpu_capability.value = 1.21
        memory_capability = Mock()
        memory_capability.name = "MemoryGB"
        memory_capability.value = 41
        capabilities_list = [vcpu_capability, memory_capability]
        self.bad_standard_a5_definition.capabilities = capabilities_list
        self.bad_json = json.dumps(
            self.bad_standard_a5_definition, default=lambda x: x.__dict__
        )

        self.garbage_definition = Mock()
        self.garbage_definition.name = "RandomAzureObject"
        self.garbage_definition.resource_type = "notVirtualMachines"

    @patch(f"{_MAINTENANCE}.ComputeManagementClient")
    def test_repopulate_azure_instance_mapping(self, mock_compute):
        """Test that repopulate_azure_instance_mapping creates db objects."""
        resource_skus = mock_compute.return_value.resource_skus
        resource_skus.list = MagicMock(
            return_value=[self.standard_a5_definition, self.garbage_definition]
        )

        tasks.repopulate_azure_instance_mapping()

        mock_compute.assert_called_once()
        resource_skus.list.assert_called_once()
        obj = InstanceDefinition.objects.get(instance_type="Standard_A5")
        self.assertEqual(obj.cloud_type, "azure")
        self.assertEqual(obj.memory_mib, self.good_14GB_to_MiB)
        self.assertEqual(obj.vcpu, Decimal("0.75"))

    @patch(f"{_MAINTENANCE}.ComputeManagementClient")
    def test_repopulate_azure_instance_mapping_exists(
        self,
        mock_compute,
    ):
        """Test that repopulate job ignores already created objects."""
        obj, __ = InstanceDefinition.objects.get_or_create(
            instance_type="Standard_A5",
            memory_mib=bitmath.GB(14).to_MiB(),
            vcpu=0.75,
            cloud_type="azure",
            json_definition=self.good_json,
        )

        resource_skus = mock_compute.return_value.resource_skus
        resource_skus.list = MagicMock(
            return_value=[
                self.bad_standard_a5_definition,
            ]
        )

        tasks.repopulate_azure_instance_mapping()
        obj.refresh_from_db()
        # Make sure that the instance did not change
        # As Azure would not change existing definitions
        self.assertEqual(obj.vcpu, Decimal("0.75"))
        # Azure reports memory in GB, but we store it as MiB.
        self.assertEqual(obj.memory_mib, self.good_14GB_to_MiB)

        self.assertEqual(obj.json_definition, self.good_json)

    @patch(f"{_MAINTENANCE}._fetch_azure_instance_type_definitions")
    @patch(f"{_MAINTENANCE}.save_instance_type_definitions")
    def test_repopulate_ec2_instance_mapping_error_on_save(self, mock_save, mock_fetch):
        """Test that repopulate_azure_instance_mapping handles error on save."""
        mock_save.side_effect = Exception()
        with self.assertRaises(Exception):
            tasks.repopulate_azure_instance_mapping()
