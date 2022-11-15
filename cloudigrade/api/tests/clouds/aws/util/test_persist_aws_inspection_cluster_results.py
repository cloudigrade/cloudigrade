"""Collection of tests for api.cloud.aws.util.persist_aws_inspection_cluster_results."""
import faker
from django.test import TestCase

from api.clouds.aws import util
from api.clouds.aws.models import AwsMachineImage
from api.tests import helper as api_helper
from util.exceptions import InvalidHoundigradeJsonFormat
from util.tests import helper as util_helper

_faker = faker.Faker()


class PersistAwsInspectionClusterResultsTest(TestCase):
    """Celery task 'persist_aws_inspection_cluster_results' test cases."""

    def test_persist_aws_inspection_cluster_results_mark_rhel(self):
        """Assert that rhel_images are tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        api_helper.generate_image(
            is_encrypted=False, is_windows=False, ec2_ami_id=ami_id
        )
        rhel_version = _faker.slug()
        syspurpose = {_faker.slug(): _faker.text()}
        inspection_results = {
            "cloud": "aws",
            "images": {
                ami_id: {
                    "rhel_found": True,
                    "rhel_release_files_found": True,
                    "rhel_version": rhel_version,
                    "syspurpose": syspurpose,
                    "drive": {
                        "partition": {
                            "facts": [
                                {
                                    "release_file": "/redhat-release",
                                    "release_file_contents": "RHEL\n",
                                    "rhel_found": True,
                                }
                            ]
                        }
                    },
                    "errors": [],
                }
            },
        }

        util.persist_aws_inspection_cluster_results(inspection_results)
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertTrue(machine_image.rhel_detected)
        self.assertEqual(
            machine_image.inspection_json,
            inspection_results["images"][ami_id],
        )
        self.assertTrue(machine_image.rhel)
        self.assertEqual(machine_image.rhel_version, rhel_version)
        self.assertFalse(machine_image.openshift)

    def test_persist_aws_inspection_cluster_results(self):
        """Assert that non rhel_images are not tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        api_helper.generate_image(
            is_encrypted=False, is_windows=False, ec2_ami_id=ami_id
        )

        inspection_results = {
            "cloud": "aws",
            "images": {
                ami_id: {
                    "rhel_found": False,
                    "rhel_version": None,
                    "syspurpose": None,
                    "drive": {
                        "partition": {
                            "facts": [
                                {
                                    "release_file": "/centos-release",
                                    "release_file_contents": "CentOS\n",
                                    "rhel_found": False,
                                }
                            ]
                        }
                    },
                    "errors": [],
                }
            },
        }

        util.persist_aws_inspection_cluster_results(inspection_results)
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertFalse(machine_image.rhel_detected)
        self.assertFalse(machine_image.openshift_detected)
        self.assertEqual(
            machine_image.inspection_json,
            inspection_results["images"][ami_id],
        )
        self.assertFalse(machine_image.rhel)
        self.assertIsNone(machine_image.rhel_version)
        self.assertIsNone(machine_image.syspurpose)
        self.assertFalse(machine_image.openshift)

    def test_persist_aws_inspection_cluster_results_our_model_is_gone(self):
        """
        Assert that we handle when the AwsMachineImage model has been deleted.

        This can happen if the customer deletes their cloud account while we
        are running or waiting on the async inspection. Deleting the cloud
        account results in the instances and potentially the images being
        deleted, and when we get the inspection results back for that deleted
        image, we should just quietly drop the results and move on to other
        results that may still need processing.
        """
        deleted_ami_id = util_helper.generate_dummy_image_id()

        ami_id = util_helper.generate_dummy_image_id()
        api_helper.generate_image(
            is_encrypted=False, is_windows=False, ec2_ami_id=ami_id
        )
        rhel_version_a = _faker.slug()
        rhel_version_b = _faker.slug()

        inspection_results = {
            "cloud": "aws",
            "images": {
                deleted_ami_id: {
                    "rhel_found": True,
                    "rhel_release_files_found": True,
                    "rhel_version": rhel_version_b,
                },
                ami_id: {
                    "rhel_found": True,
                    "rhel_release_files_found": True,
                    "rhel_version": rhel_version_a,
                },
            },
        }

        util.persist_aws_inspection_cluster_results(inspection_results)
        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertTrue(machine_image.rhel)
        self.assertEqual(machine_image.rhel_version, rhel_version_a)

        with self.assertRaises(AwsMachineImage.DoesNotExist):
            AwsMachineImage.objects.get(ec2_ami_id=deleted_ami_id)

    def test_persist_aws_inspection_cluster_results_no_images(self):
        """Assert that non rhel_images are not tagged rhel."""
        ami_id = util_helper.generate_dummy_image_id()
        api_helper.generate_image(
            is_encrypted=False, is_windows=False, ec2_ami_id=ami_id
        )

        inspection_results = {"cloud": "aws"}
        expected_message = "Inspection results json missing images: {}".format(
            inspection_results
        )

        with self.assertRaises(InvalidHoundigradeJsonFormat) as e:
            util.persist_aws_inspection_cluster_results(inspection_results)
        self.assertIn(expected_message, str(e.exception))

    def test_persist_aws_inspection_cluster_results_image_has_errors(self):
        """Assert that inspection results with image errors are logged."""
        ami_id = util_helper.generate_dummy_image_id()
        api_helper.generate_image(
            is_encrypted=False, is_windows=False, ec2_ami_id=ami_id
        )

        error_message = _faker.sentence()
        inspection_results = {
            "cloud": "aws",
            "images": {
                ami_id: {
                    "rhel_found": False,
                    "rhel_version": None,
                    "syspurpose": None,
                    "errors": [error_message],
                }
            },
        }

        with self.assertLogs("api.clouds.aws.util", level="INFO") as logging_watcher:
            util.persist_aws_inspection_cluster_results(inspection_results)
            self.assertIn(
                "Error reported in inspection results for image",
                logging_watcher.output[0],
            )
            self.assertIn(ami_id, logging_watcher.output[0])
            self.assertIn(error_message, logging_watcher.output[0])

        aws_machine_image = AwsMachineImage.objects.get(ec2_ami_id=ami_id)
        machine_image = aws_machine_image.machine_image.get()
        self.assertFalse(machine_image.rhel_detected)
