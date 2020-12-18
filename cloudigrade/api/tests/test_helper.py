"""Collection of tests for ``account.tests.helper`` module.

Because even test helpers should be tested!
"""
import http
import json
import re
import uuid
from decimal import Decimal
from unittest.mock import patch

import faker
from django.conf import settings
from django.test import TestCase
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from api.clouds.aws.models import (
    CLOUD_ACCESS_NAME_TOKEN,
    MARKETPLACE_NAME_TOKEN,
)
from api.models import (
    CloudAccount,
    Instance,
    InstanceDefinition,
    InstanceEvent,
    MachineImage,
)
from api.tests import helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class SandboxedRestClientTest(TestCase):
    """SandboxedRestClient tests."""

    def setUp(self):
        """Set up user for the client tests."""
        self.username = _faker.random_int(min=100000, max=999999)
        self.password = _faker.slug()
        self.user = util_helper.generate_test_user(self.username, self.password)

    def test_list_noun(self):
        """Assert "list" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.user)
        response = client.list_accounts()
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        response_json = response.json()
        self.assertIn("data", response_json)
        self.assertIsInstance(response_json["data"], list)
        self.assertIn("meta", response_json)
        self.assertIn("count", response_json["meta"])
        self.assertIn("links", response_json)
        self.assertIn("next", response_json["links"])
        self.assertIn("previous", response_json["links"])
        self.assertIn("first", response_json["links"])
        self.assertIn("last", response_json["links"])

    @patch("api.models.notify_sources_application_availability")
    def test_create_noun(self, mock_notify_sources):
        """Assert "create" requests work."""
        client = helper.SandboxedRestClient(api_root="/internal/api/cloudigrade/v1")
        client._force_authenticate(self.user)
        arn = util_helper.generate_dummy_arn()
        name = _faker.sentence()
        data = util_helper.generate_dummy_aws_cloud_account_post_data()
        data.update({"account_arn": arn, "name": name})
        response = client.create_accounts(data=data)
        self.assertEqual(response.status_code, http.HTTPStatus.CREATED)
        response_json = response.json()
        self.assertEqual(response_json["content_object"]["account_arn"], arn)
        self.assertEqual(response_json["name"], name)
        self.assertEqual(response_json["user_id"], self.user.id)

    def test_get_noun(self):
        """Assert "get" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.user)
        account = helper.generate_cloud_account(user=self.user)
        response = client.get_accounts(account.id)
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        response_json = response.json()
        self.assertEqual(response_json["account_id"], account.id)

    def test_invalid_request(self):
        """Assert invalid requests raise AttributeError."""
        client = helper.SandboxedRestClient()
        with self.assertRaises(AttributeError):
            client.foo_bar()

    def test_action_noun_verb_detail(self):
        """Assert "detail" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.user)

        account = helper.generate_cloud_account(user=self.user)
        image = helper.generate_image(status=MachineImage.INSPECTED)
        helper.generate_instance(account, image=image)

        response = client.post_machineimages(
            noun_id=image.id,
            detail="reinspect",
            api_root="/internal/api/cloudigrade/v1",
        )
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        self.assertEqual(MachineImage.PENDING, response.data["status"])


class GenerateCloudAccountTest(TestCase):
    """generate_cloud_account tests."""

    def test_generate_aws_account_default(self):
        """Assert generation of an AwsAccount with default/no args."""
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        with util_helper.clouditardis(created_at):
            account = helper.generate_cloud_account()
        self.assertIsInstance(account, CloudAccount)
        self.assertIsNotNone(
            re.match(r"\d{1,12}", str(account.content_object.aws_account_id))
        )
        self.assertEqual(account.created_at, created_at)
        self.assertTrue(account.is_enabled)
        self.assertEqual(account.enabled_at, created_at)
        self.assertIsNotNone(account.platform_authentication_id)
        self.assertIsNotNone(account.platform_application_id)
        self.assertIsNotNone(account.platform_source_id)
        self.assertIsNotNone(account.content_object.verify_task)

    def test_generate_azure_account_default(self):
        """Assert generation of an AwsAccount with default/no args."""
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        with util_helper.clouditardis(created_at):
            account = helper.generate_cloud_account(cloud_type="azure")
        self.assertIsInstance(account, CloudAccount)
        self.assertIsNotNone(account.content_object.subscription_id)
        self.assertIsNotNone(account.content_object.tenant_id)
        self.assertEqual(account.created_at, created_at)
        self.assertTrue(account.is_enabled)
        self.assertEqual(account.enabled_at, created_at)
        self.assertIsNotNone(account.platform_authentication_id)
        self.assertIsNotNone(account.platform_application_id)
        self.assertIsNotNone(account.platform_source_id)

    def test_generate_aws_account_with_args(self):
        """Assert generation of an AwsAccount with all specified args."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        user = util_helper.generate_test_user()
        name = _faker.name()
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        platform_authentication_id = _faker.pyint()
        platform_application_id = _faker.pyint()
        platform_source_id = _faker.pyint()
        is_enabled = False
        enabled_at = util_helper.utc_dt(2017, 1, 2, 0, 0, 0)

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=settings.SCHEDULE_VERIFY_VERIFY_TASKS_INTERVAL,
            period=IntervalSchedule.SECONDS,
        )
        verify_task, _ = PeriodicTask.objects.get_or_create(
            interval=schedule,
            name=f"Verify {arn}.",
            task="api.clouds.aws.tasks.verify_account_permissions",
            kwargs=json.dumps(
                {
                    "account_arn": arn,
                }
            ),
            defaults={"start_time": created_at},
        )

        account = helper.generate_cloud_account(
            arn,
            aws_account_id,
            user,
            name,
            created_at,
            platform_authentication_id,
            platform_application_id,
            platform_source_id,
            is_enabled,
            enabled_at,
            verify_task,
        )
        self.assertIsInstance(account, CloudAccount)
        self.assertEqual(account.content_object.account_arn, arn)
        self.assertEqual(account.content_object.aws_account_id, aws_account_id)

        self.assertEqual(account.platform_authentication_id, platform_authentication_id)
        self.assertEqual(account.platform_application_id, platform_application_id)
        self.assertEqual(account.platform_source_id, platform_source_id)
        self.assertEqual(account.user, user)
        self.assertEqual(account.name, name)
        self.assertEqual(account.created_at, created_at)
        self.assertFalse(account.is_enabled)
        self.assertEqual(account.enabled_at, enabled_at)
        self.assertEqual(account.content_object.verify_task, verify_task)


class GenerateInstanceTest(TestCase):
    """generate_instance test case."""

    def test_generate_aws_instance_default(self):
        """Assert generation of an Instance with minimal args."""
        account = helper.generate_cloud_account()
        instance = helper.generate_instance(account)
        self.assertIsInstance(instance, Instance)
        self.assertEqual(instance.cloud_account, account)
        self.assertIsNotNone(instance.content_object.ec2_instance_id)
        self.assertGreater(len(instance.content_object.ec2_instance_id), 0)
        self.assertIsNotNone(instance.content_object.region)
        self.assertGreater(len(instance.content_object.region), 0)

    def test_generate_azure_instance_default(self):
        """Assert generation of an Instance with minimal args."""
        account = helper.generate_cloud_account(cloud_type="azure")
        instance = helper.generate_instance(account, cloud_type="azure")
        self.assertIsInstance(instance, Instance)
        self.assertEqual(instance.cloud_account, account)
        self.assertIsNotNone(instance.content_object.resource_id)
        self.assertIsNotNone(instance.content_object.region)
        self.assertGreater(len(instance.content_object.region), 0)

    def test_generate_aws_instance_with_args(self):
        """Assert generation of an AwsInstance with all specified args."""
        account = helper.generate_cloud_account()
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        region = util_helper.get_random_region()
        instance = helper.generate_instance(
            account,
            ec2_instance_id=ec2_instance_id,
            region=region,
        )
        self.assertIsInstance(instance, Instance)
        self.assertEqual(instance.cloud_account, account)
        self.assertEqual(instance.content_object.ec2_instance_id, ec2_instance_id)
        self.assertEqual(instance.content_object.region, region)


class GenerateInstanceEventsTest(TestCase):
    """generate_instance_events test case."""

    def test_generate_aws_events_default_and_no_times(self):
        """Assert generation of InstanceEvents with minimal args."""
        account = helper.generate_cloud_account()
        instance = helper.generate_instance(account)
        events = helper.generate_instance_events(instance, tuple())
        self.assertEqual(len(events), 0)

    def test_generate_azure_events_default_and_no_times(self):
        """Assert generation of an azure InstanceEvent."""
        account = helper.generate_cloud_account(cloud_type="azure")
        instance = helper.generate_instance(account, cloud_type="azure")
        events = helper.generate_instance_events(instance, tuple(), cloud_type="azure")
        self.assertEqual(len(events), 0)

    def test_generate_aws_events_with_some_times(self):
        """Assert generation of InstanceEvents with some times."""
        account = helper.generate_cloud_account()
        instance = helper.generate_instance(account)
        powered_times = (
            (None, util_helper.utc_dt(2017, 1, 1)),
            (util_helper.utc_dt(2017, 1, 2), util_helper.utc_dt(2017, 1, 3)),
            (util_helper.utc_dt(2017, 1, 4), None),
        )
        events = helper.generate_instance_events(instance, powered_times)

        self.assertEqual(len(events), 4)
        self.assertEqual(events[0].occurred_at, powered_times[0][1])
        self.assertEqual(events[1].occurred_at, powered_times[1][0])
        self.assertEqual(events[2].occurred_at, powered_times[1][1])
        self.assertEqual(events[3].occurred_at, powered_times[2][0])

        self.assertEqual(events[0].event_type, InstanceEvent.TYPE.power_off)
        self.assertEqual(events[1].event_type, InstanceEvent.TYPE.power_on)
        self.assertEqual(events[2].event_type, InstanceEvent.TYPE.power_off)
        self.assertEqual(events[3].event_type, InstanceEvent.TYPE.power_on)

        self.assertIsNotNone(events[0].content_object.instance_type)
        self.assertIsNotNone(events[0].content_object.subnet)

        # Assert they all have the same AMI, subnet, and instance type.
        for event in events[1:]:
            self.assertEqual(
                event.content_object.instance_type,
                events[0].content_object.instance_type,
            )
            self.assertEqual(
                event.content_object.subnet, events[0].content_object.subnet
            )
            if event.event_type != event.TYPE.power_off:
                # power_off events typically don't have an image defined.
                # the second event should be power_on and should have an
                # image defined we can compare with.
                self.assertEqual(
                    event.instance.machine_image, events[1].instance.machine_image
                )

    def test_generate_aws_events_with_args_and_some_times(self):
        """Assert generation of InstanceEvents with all specified args."""
        account = helper.generate_cloud_account()
        ec2_ami_id = util_helper.generate_dummy_image_id()
        image = helper.generate_image(ec2_ami_id=ec2_ami_id)
        instance = helper.generate_instance(account, image=image)
        powered_times = (
            (None, util_helper.utc_dt(2017, 1, 1)),
            (util_helper.utc_dt(2017, 1, 2), util_helper.utc_dt(2017, 1, 3)),
            (util_helper.utc_dt(2017, 1, 4), None),
        )
        instance_type = util_helper.get_random_instance_type()
        subnet = str(uuid.uuid4())
        events = helper.generate_instance_events(
            instance,
            powered_times,
            instance_type=instance_type,
            subnet=subnet,
        )

        self.assertEqual(len(events), 4)
        # We don't care to check *everything* in the events since that should
        # already be covered by ``test_generate_events_with_some_times``.
        # Here we only care that argument values were set correctly.
        for event in events:
            if event.event_type != event.TYPE.power_off:
                self.assertEqual(
                    event.instance.machine_image.content_object.ec2_ami_id, ec2_ami_id
                )
            self.assertEqual(event.content_object.instance_type, instance_type)
            self.assertEqual(event.content_object.subnet, subnet)


class GenerateAwsImageTest(TestCase):
    """generate_aws_image test case."""

    def test_generate_aws_image_default(self):
        """Assert generation of an AwsMachineImage with minimal args."""
        image = helper.generate_image()
        self.assertIsInstance(image.content_object.owner_aws_account_id, Decimal)
        self.assertEqual(image.content_object.platform, image.content_object.NONE)
        self.assertIsNotNone(image.content_object.ec2_ami_id)
        self.assertGreater(len(image.content_object.ec2_ami_id), 0)
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.rhel_detected_by_tag)
        self.assertFalse(image.openshift_detected)
        self.assertIsNone(image.name)
        self.assertIsNone(image.rhel_version)
        self.assertIsNone(image.syspurpose)
        self.assertFalse(image.content_object.is_cloud_access)
        self.assertFalse(image.content_object.is_marketplace)
        self.assertEqual(image.architecture, "x86_64")

    def test_generate_aws_image_with_args(self):
        """Assert generation of an AwsMachineImage with all specified args."""
        account_id = util_helper.generate_dummy_aws_account_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()
        name = _faker.name()
        rhel_version = _faker.slug()
        syspurpose = {_faker.slug(): _faker.text()}
        architecture = _faker.slug()

        image = helper.generate_image(
            account_id,
            is_encrypted=True,
            is_windows=True,
            ec2_ami_id=ec2_ami_id,
            rhel_detected=True,
            rhel_detected_by_tag=True,
            rhel_detected_repos=True,
            rhel_detected_certs=True,
            rhel_detected_release_files=True,
            rhel_detected_signed_packages=True,
            rhel_version=rhel_version,
            syspurpose=syspurpose,
            openshift_detected=True,
            name=name,
            status=MachineImage.PREPARING,
            architecture=architecture,
        )

        self.assertIsInstance(image, MachineImage)
        self.assertEqual(image.content_object.owner_aws_account_id, account_id)
        self.assertEqual(image.content_object.platform, image.content_object.WINDOWS)
        self.assertEqual(image.content_object.ec2_ami_id, ec2_ami_id)
        self.assertTrue(image.rhel_detected)
        self.assertTrue(image.rhel_detected_by_tag)
        self.assertEqual(image.rhel_version, rhel_version)
        self.assertEqual(image.syspurpose, syspurpose)
        self.assertTrue(image.openshift_detected)
        self.assertEqual(image.name, name)
        self.assertEqual(image.status, MachineImage.PREPARING)
        self.assertFalse(image.content_object.is_cloud_access)
        self.assertFalse(image.content_object.is_marketplace)
        self.assertEqual(image.architecture, architecture)

    def test_generate_aws_image_with_rhel_detected_details_args(self):
        """Assert generation of an AwsMachineImage with RHEL JSON details."""
        rhel_version = _faker.slug()
        image = helper.generate_image(
            rhel_detected=True,
            rhel_detected_repos=True,
            rhel_detected_certs=True,
            rhel_detected_release_files=True,
            rhel_detected_signed_packages=True,
            rhel_version=rhel_version,
        )

        self.assertIsInstance(image, MachineImage)
        self.assertIsNotNone(image.inspection_json)
        inspection_data = json.loads(image.inspection_json)
        self.assertTrue(inspection_data["rhel_enabled_repos_found"])
        self.assertTrue(inspection_data["rhel_product_certs_found"])
        self.assertTrue(inspection_data["rhel_release_files_found"])
        self.assertTrue(inspection_data["rhel_signed_packages_found"])
        self.assertEqual(image.rhel_version, rhel_version)

    def test_generate_aws_image_with_is_cloud_access(self):
        """Assert generation of an AwsMachineImage with is_cloud_access."""
        account_id = util_helper.generate_dummy_aws_account_id()
        name = _faker.name()

        image = helper.generate_image(
            account_id,
            name=name,
            is_cloud_access=True,
        )

        self.assertNotEqual(image.content_object.owner_aws_account_id, account_id)
        self.assertIn(
            image.content_object.owner_aws_account_id, settings.RHEL_IMAGES_AWS_ACCOUNTS
        )
        self.assertTrue(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertNotEqual(image.name, name)
        self.assertIn(CLOUD_ACCESS_NAME_TOKEN, image.name)
        self.assertTrue(image.content_object.is_cloud_access)
        self.assertFalse(image.content_object.is_marketplace)

    def test_generate_aws_image_with_is_marketplace(self):
        """Assert generation of an AwsMachineImage with is_marketplace."""
        account_id = util_helper.generate_dummy_aws_account_id()
        name = _faker.name()

        image = helper.generate_image(
            account_id,
            name=name,
            is_marketplace=True,
        )

        self.assertNotEqual(image.content_object.owner_aws_account_id, account_id)
        self.assertIn(
            image.content_object.owner_aws_account_id, settings.RHEL_IMAGES_AWS_ACCOUNTS
        )
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertNotEqual(image.name, name)
        self.assertIn(MARKETPLACE_NAME_TOKEN, image.name)
        self.assertFalse(image.content_object.is_cloud_access)
        self.assertTrue(image.content_object.is_marketplace)


class GenerateInstanceDefinitionsTest(TestCase):
    """generate_aws_ec2_definitions test case."""

    def test_generate_aws_ec2_definitions_when_empty(self):
        """Assert generation of AWS EC2 instance definitions."""
        self.assertEqual(InstanceDefinition.objects.count(), 0)
        helper.generate_instance_type_definitions()
        self.assertEqual(
            InstanceDefinition.objects.count(),
            len(util_helper.SOME_EC2_INSTANCE_TYPES),
        )

    @patch.object(helper, "logger")
    def test_generate_aws_ec2_definitions_warns_when_not_empty(self, mock_logger):
        """Assert warning when generating definition that already exists."""
        helper.generate_instance_type_definitions()
        helper.generate_instance_type_definitions()
        self.assertEqual(
            InstanceDefinition.objects.count(),
            len(util_helper.SOME_EC2_INSTANCE_TYPES),
        )
        # warning counts should match because each type was attempted twice.
        self.assertEqual(
            len(mock_logger.warning.mock_calls),
            len(util_helper.SOME_EC2_INSTANCE_TYPES),
        )
