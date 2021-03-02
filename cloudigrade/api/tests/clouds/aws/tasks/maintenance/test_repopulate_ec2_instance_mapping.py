"""Collection of tests for aws.tasks.cloudtrail.repopulate_ec2_instance_mapping."""
import json
from unittest.mock import Mock, patch

import faker
from django.db import IntegrityError
from django.test import TestCase

from api.clouds.aws import tasks
from api.models import InstanceDefinition

_faker = faker.Faker()

# Token for this string since some of the paths in "patch" uses are very long.
_MAINTENANCE = "api.clouds.aws.tasks.maintenance"

R5LARGE_DEFINITION = {
    "AutoRecoverySupported": True,
    "BareMetal": False,
    "BurstablePerformanceSupported": False,
    "CurrentGeneration": True,
    "DedicatedHostsSupported": True,
    "EbsInfo": {"EbsOptimizedSupport": "default", "EncryptionSupport": "supported"},
    "FreeTierEligible": False,
    "HibernationSupported": True,
    "Hypervisor": "nitro",
    "InstanceStorageSupported": False,
    "InstanceType": "r5.large",
    "MemoryInfo": {"SizeInMiB": 16384},
    "NetworkInfo": {
        "EnaSupport": "required",
        "Ipv4AddressesPerInterface": 10,
        "Ipv6AddressesPerInterface": 10,
        "Ipv6Supported": True,
        "MaximumNetworkInterfaces": 3,
        "NetworkPerformance": "Up to 10 Gigabit",
    },
    "PlacementGroupInfo": {"SupportedStrategies": ["cluster", "partition", "spread"]},
    "ProcessorInfo": {
        "SupportedArchitectures": ["x86_64"],
        "SustainedClockSpeedInGhz": 3.1,
    },
    "SupportedRootDeviceTypes": ["ebs"],
    "SupportedUsageClasses": ["on-demand", "spot"],
    "VCpuInfo": {
        "DefaultCores": 1,
        "DefaultThreadsPerCore": 2,
        "DefaultVCpus": 2,
        "ValidCores": [1],
        "ValidThreadsPerCore": [1, 2],
    },
}

BAD_R5LARGE_DEFINITION = {
    "InstanceType": "r5.large",
    "MemoryInfo": {"SizeInMiB": 16380},
    "ProcessorInfo": {
        "SupportedArchitectures": ["x86_64"],
        "SustainedClockSpeedInGhz": 3.1,
    },
    "VCpuInfo": {
        "DefaultCores": 1,
        "DefaultThreadsPerCore": 2,
        "DefaultVCpus": 1,
        "ValidCores": [1],
        "ValidThreadsPerCore": [1, 2],
    },
}

REGION_LIST = {
    "Regions": [
        {"RegionName": "us-east-1"},
        {"RegionName": "us-east-2"},
    ]
}


class RepopulateEc2InstanceMappingTest(TestCase):
    """Celery task 'repopulate_ec2_instance_mapping' test cases."""

    @patch(f"{_MAINTENANCE}.InstanceDefinition.objects.get_or_create")
    @patch(f"{_MAINTENANCE}.boto3.client")
    def test_repopulate_ec2_instance_mapping(self, mock_boto3, mock_db_create):
        """Test that repopulate_ec2_instance_mapping creates db objects."""
        mock_instance_def = Mock()
        mock_instance_def.instance_type.return_value = "r5.large"
        mock_db_create.return_value = (mock_instance_def, True)
        mock_boto3.return_value.describe_regions.return_value = REGION_LIST
        paginator = mock_boto3.return_value.get_paginator.return_value
        paginator.paginate.return_value = [{"InstanceTypes": [R5LARGE_DEFINITION]}]
        tasks.repopulate_ec2_instance_mapping()
        mock_db_create.assert_called_with(
            defaults={
                "memory": 16384,
                "vcpu": 2,
                "json_definition": json.dumps(R5LARGE_DEFINITION),
            },
            instance_type="r5.large",
            cloud_type="aws",
        )

    @patch(f"{_MAINTENANCE}.boto3.client")
    def test_repopulate_ec2_instance_mapping_exists(
        self,
        mock_boto3,
    ):
        """Test that repopulate job ignores already created objects."""
        obj, __ = InstanceDefinition.objects.get_or_create(
            instance_type="r5.large",
            memory=16384,
            vcpu=2,
            cloud_type="aws",
            json_definition=json.dumps(R5LARGE_DEFINITION),
        )
        mock_boto3.return_value.describe_regions.return_value = REGION_LIST
        paginator = mock_boto3.return_value.get_paginator.return_value
        paginator.paginate.return_value = [{"InstanceTypes": [BAD_R5LARGE_DEFINITION]}]
        tasks.repopulate_ec2_instance_mapping()
        obj.refresh_from_db()
        # Make sure that the instance did not change
        # As AWS would not change existing definitions
        self.assertEqual(obj.vcpu, 2)
        self.assertEqual(obj.memory, 16384)
        self.assertEqual(obj.json_definition, json.dumps(R5LARGE_DEFINITION))

    @patch(f"{_MAINTENANCE}.repopulate_ec2_instance_mapping.delay")
    @patch(f"{_MAINTENANCE}.InstanceDefinition.objects.get")
    def test_get_instance_definition_returns_value_in_db(self, mock_lookup, mock_remap):
        """Test that task isn't run if instance definition already exists."""
        mock_instance_definition = Mock()
        mock_instance_definition.instance_type = "t3.nano"
        mock_instance_definition.memory = "0.5"
        mock_instance_definition.vcpu = "2"
        mock_lookup.return_value = mock_instance_definition

        instance = mock_lookup()
        self.assertEqual(mock_instance_definition, instance)
        mock_remap.assert_not_called()

    @patch(f"{_MAINTENANCE}._fetch_ec2_instance_type_definitions")
    @patch(f"{_MAINTENANCE}._save_ec2_instance_type_definitions")
    def test_repopulate_ec2_instance_mapping_error_on_save(self, mock_save, mock_fetch):
        """Test that repopulate_ec2_instance_mapping handles error on save."""
        mock_save.side_effect = Exception()
        with self.assertRaises(Exception):
            tasks.repopulate_ec2_instance_mapping()

    @patch(f"{_MAINTENANCE}.InstanceDefinition.objects.get_or_create")
    def test_save_ec2_instance_type_definitions_mystery_integrity_error(
        self, mock_get_or_create
    ):
        """Test _save_ec2_instance_type_definitions handles mystery error."""
        mock_get_or_create.side_effect = IntegrityError("it is a mystery")
        definitions = {
            "r5.large": {"memory": 420, "vcpu": 69, "json_definition": {"foo": "bar"}}
        }
        with self.assertRaises(IntegrityError):
            tasks.maintenance._save_ec2_instance_type_definitions(definitions)
