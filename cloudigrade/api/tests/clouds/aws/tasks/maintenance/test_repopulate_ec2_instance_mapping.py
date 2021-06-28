"""Collection of tests for aws.tasks.cloudtrail.repopulate_ec2_instance_mapping."""
import json
from unittest.mock import Mock, patch

import faker
from django.db import IntegrityError
from django.test import TestCase

from api import AWS_PROVIDER_STRING
from api.clouds.aws import tasks
from api.models import InstanceDefinition
from api.util import save_instance_type_definitions

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

    @patch(f"{_MAINTENANCE}.boto3.client")
    def test_repopulate_ec2_instance_mapping(self, mock_boto3):
        """Test that repopulate_ec2_instance_mapping creates db objects."""
        mock_instance_def = Mock()
        mock_instance_def.instance_type.return_value = "r5.large"
        mock_boto3.return_value.describe_regions.return_value = REGION_LIST
        paginator = mock_boto3.return_value.get_paginator.return_value
        paginator.paginate.return_value = [{"InstanceTypes": [R5LARGE_DEFINITION]}]
        tasks.repopulate_ec2_instance_mapping()

        obj = InstanceDefinition.objects.get(instance_type="r5.large")
        self.assertEqual(obj.cloud_type, "aws")
        self.assertEqual(obj.vcpu, 2)
        self.assertEqual(obj.memory_mib, 16384)
        self.assertEqual(obj.json_definition, json.dumps(R5LARGE_DEFINITION))

    @patch(f"{_MAINTENANCE}.boto3.client")
    def test_repopulate_ec2_instance_mapping_exists(
        self,
        mock_boto3,
    ):
        """Test that repopulate job ignores already created objects."""
        obj, __ = InstanceDefinition.objects.get_or_create(
            instance_type="r5.large",
            memory_mib=16384,
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
        self.assertEqual(obj.memory_mib, 16384)
        self.assertEqual(obj.json_definition, json.dumps(R5LARGE_DEFINITION))

    @patch(f"{_MAINTENANCE}._fetch_ec2_instance_type_definitions")
    @patch(f"{_MAINTENANCE}.save_instance_type_definitions")
    def test_repopulate_ec2_instance_mapping_error_on_save(self, mock_save, mock_fetch):
        """Test that repopulate_ec2_instance_mapping handles error on save."""
        mock_save.side_effect = Exception()
        with self.assertRaises(Exception):
            tasks.repopulate_ec2_instance_mapping()

    @patch("api.util.InstanceDefinition.objects.get_or_create")
    def test_save_ec2_instance_type_definitions_mystery_integrity_error(
        self, mock_get_or_create
    ):
        """Test save_instance_type_definitions handles mystery error."""
        mock_get_or_create.side_effect = IntegrityError("it is a mystery")
        definitions = {
            "r5.large": {"memory": 420, "vcpu": 69, "json_definition": {"foo": "bar"}}
        }
        with self.assertRaises(IntegrityError):
            save_instance_type_definitions(definitions, AWS_PROVIDER_STRING)
