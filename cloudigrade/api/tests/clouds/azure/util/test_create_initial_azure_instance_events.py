"""Collection of tests for api.cloud.azure.util.create_new_machine_images."""
from unittest.mock import patch

import faker
from django.test import TestCase

from api.clouds.azure import util
from api.clouds.azure.models import AzureInstance, AzureInstanceEvent
from api.models import CloudAccount, InstanceEvent
from util.tests import helper as util_helper

_faker = faker.Faker()


class CreateInitialAzureInstanceEvents(TestCase):
    """Test cases for api.cloud.azure.util.create_initial_azure_instance_events."""

    def setUp(self):
        """Set up shared variables."""
        self.user = util_helper.generate_test_user()
        self.subscription_id = _faker.uuid4()
        self.auth_id = _faker.pyint()
        self.app_id = _faker.pyint()
        self.source_id = _faker.pyint()

    @patch.object(CloudAccount, "enable")
    def test_create_initial_azure_instance_events(self, mock_enable):
        """Tests creation of two machine instances, one stopped and one running."""
        azure_cloud_account = util.create_azure_cloud_account(
            self.user, self.subscription_id, self.auth_id, self.app_id, self.source_id
        )
        vm1 = util_helper.generate_vm_data()
        vm2 = util_helper.generate_vm_data(running=True)
        util.create_initial_azure_instance_events(azure_cloud_account, [vm1, vm2])
        mock_enable.assert_called()
        self.assertTrue(AzureInstance.objects.count() == 2)
        self.assertTrue(AzureInstance.objects.filter(resource_id=vm1["id"]).exists())
        self.assertTrue(AzureInstance.objects.filter(resource_id=vm2["id"]).exists())
        self.assertTrue(AzureInstanceEvent.objects.count() == 1)
        self.assertTrue(InstanceEvent.objects.count() == 1)
        self.assertEqual(
            InstanceEvent.objects.first().event_type, InstanceEvent.TYPE.power_on
        )
