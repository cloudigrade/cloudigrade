"""Collection of tests for aws.tasks.cloudtrail.repopulate_ec2_instance_mapping."""
from unittest.mock import Mock, patch

import faker
from django.db import IntegrityError
from django.test import TestCase

from api.clouds.aws import tasks
from api.models import InstanceDefinition

_faker = faker.Faker()

# Token for this string since some of the paths in "patch" uses are very long.
_MAINTENANCE = "api.clouds.aws.tasks.maintenance"


class RepopulateEc2InstanceMappingTest(TestCase):
    """Celery task 'repopulate_ec2_instance_mapping' test cases."""

    @patch(f"{_MAINTENANCE}.InstanceDefinition.objects.get_or_create")
    @patch(f"{_MAINTENANCE}.boto3.client")
    def test_repopulate_ec2_instance_mapping(self, mock_boto3, mock_db_create):
        """Test that repopulate_ec2_instance_mapping creates db objects."""
        mock_instance_def = Mock()
        mock_instance_def.instance_type.return_value = "r5.large"
        mock_db_create.return_value = (mock_instance_def, True)
        paginator = mock_boto3.return_value.get_paginator.return_value
        paginator.paginate.return_value = [
            {
                "PriceList": [
                    """{
                    "product": {
                        "productFamily": "Compute Instance",
                        "attributes": {
                            "memory": "16 GiB",
                            "vcpu": "2",
                            "capacitystatus": "Used",
                            "instanceType": "r5.large",
                            "tenancy": "Host",
                            "usagetype": "APN1-HostBoxUsage:r5.large",
                            "locationType": "AWS Region",
                            "storage": "EBS only",
                            "normalizationSizeFactor": "4",
                            "instanceFamily": "Memory optimized",
                            "operatingSystem": "RHEL",
                            "servicecode": "AmazonEC2",
                            "physicalProcessor": "Intel Xeon Platinum 8175",
                            "licenseModel": "No License required",
                            "ecu": "10",
                            "currentGeneration": "Yes",
                            "preInstalledSw": "NA",
                            "networkPerformance": "10 Gigabit",
                            "location": "Asia Pacific (Tokyo)",
                            "servicename": "Amazon Elastic Compute Cloud",
                            "processorArchitecture": "64-bit",
                            "operation": "RunInstances:0010"
                        },
                        "sku": "22WY57989R2PA7RB"
                    },
                    "serviceCode": "AmazonEC2",
                    "terms": {
                        "OnDemand": {
                            "22WY57989R2PA7RB.JRTCKXETXF": {
                                "priceDimensions": {
                                    "22WY57989R2PA7RB.JRTCKXETXF.6YS6EN2CT7": {
                                        "unit": "Hrs",
                                        "endRange": "Inf",
                                        "appliesTo": [
                                        ],
                                        "beginRange": "0",
                                        "pricePerUnit": {
                                            "USD": "0.0000000000"
                                        }
                                    }
                                },
                                "sku": "22WY57989R2PA7RB",
                                "effectiveDate": "2018-11-01T00:00:00Z",
                                "offerTermCode": "JRTCKXETXF",
                                "termAttributes": {

                                }
                            }
                        }
                    },
                    "version": "20181122020351",
                    "publicationDate": "2018-11-22T02:03:51Z"
                }"""
                ]
            }
        ]
        tasks.repopulate_ec2_instance_mapping()
        mock_db_create.assert_called_with(
            defaults={"memory": 16.0, "vcpu": 2},
            instance_type="r5.large",
            cloud_type="aws",
        )

    @patch(f"{_MAINTENANCE}.boto3.client")
    def test_repopulate_ec2_instance_mapping_exists(self, mock_boto3):
        """Test that repopulate job ignores already created objects."""
        obj, __ = InstanceDefinition.objects.get_or_create(
            instance_type="r5.large", memory=float(16), vcpu=2, cloud_type="aws"
        )
        paginator = mock_boto3.return_value.get_paginator.return_value
        paginator.paginate.return_value = [
            {
                "PriceList": [
                    """{
                    "product": {
                        "productFamily": "Compute Instance",
                        "attributes": {
                            "memory": "24 GiB",
                            "vcpu": "1",
                            "capacitystatus": "Used",
                            "instanceType": "r5.large",
                            "tenancy": "Host",
                            "usagetype": "APN1-HostBoxUsage:r5.large",
                            "locationType": "AWS Region",
                            "storage": "EBS only",
                            "normalizationSizeFactor": "4",
                            "instanceFamily": "Memory optimized",
                            "operatingSystem": "RHEL",
                            "servicecode": "AmazonEC2",
                            "physicalProcessor": "Intel Xeon Platinum 8175",
                            "licenseModel": "No License required",
                            "ecu": "10",
                            "currentGeneration": "Yes",
                            "preInstalledSw": "NA",
                            "networkPerformance": "10 Gigabit",
                            "location": "Asia Pacific (Tokyo)",
                            "servicename": "Amazon Elastic Compute Cloud",
                            "processorArchitecture": "64-bit",
                            "operation": "RunInstances:0010"
                        },
                        "sku": "22WY57989R2PA7RB"
                    },
                    "serviceCode": "AmazonEC2",
                    "terms": {
                        "OnDemand": {
                            "22WY57989R2PA7RB.JRTCKXETXF": {
                                "priceDimensions": {
                                    "22WY57989R2PA7RB.JRTCKXETXF.6YS6EN2CT7": {
                                        "unit": "Hrs",
                                        "endRange": "Inf",
                                        "appliesTo": [
                                        ],
                                        "beginRange": "0",
                                        "pricePerUnit": {
                                            "USD": "0.0000000000"
                                        }
                                    }
                                },
                                "sku": "22WY57989R2PA7RB",
                                "effectiveDate": "2018-11-01T00:00:00Z",
                                "offerTermCode": "JRTCKXETXF",
                                "termAttributes": {

                                }
                            }
                        }
                    },
                    "version": "20181122020351",
                    "publicationDate": "2018-11-22T02:03:51Z"
                }"""
                ]
            }
        ]
        tasks.repopulate_ec2_instance_mapping()
        obj.refresh_from_db()
        # Make sure that the instance did not change
        # As AWS would not change existing definitions
        self.assertEqual(obj.vcpu, 2)
        self.assertEqual(obj.memory, 16.00)

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
        definitions = {"r5.large": {"memory": 420, "vcpu": 69}}
        with self.assertRaises(IntegrityError):
            tasks.maintenance._save_ec2_instance_type_definitions(definitions)
