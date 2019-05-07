"""Collection of tests for ``account.tests.helper`` module.

Because even test helpers should be tested!
"""
import http
import re
import uuid
from decimal import Decimal
from unittest.mock import patch

import faker
from django.conf import settings
from django.test import TestCase

from account.models import (
    AwsAccount,
    AwsEC2InstanceDefinitions,
    AwsInstance,
    AwsMachineImage,
    CLOUD_ACCESS_NAME_TOKEN,
    InstanceEvent,
    MARKETPLACE_NAME_TOKEN,
)
from account.tests import helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class SandboxedRestClientTest(TestCase):
    """SandboxedRestClient tests."""

    def setUp(self):
        """Set up user for the client tests."""
        self.username = f'{_faker.slug()}@example.com'
        self.password = _faker.slug()
        self.user = util_helper.generate_test_user(
            self.username, self.password
        )
        self.superuser = util_helper.generate_test_user(
            is_superuser=True
        )

    def test_list_noun(self):
        """Assert "list" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.user)
        response = client.list_account()
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        response_json = response.json()
        self.assertIn('results', response_json)
        self.assertIsInstance(response_json['results'], list)
        self.assertIn('count', response_json)
        self.assertIn('next', response_json)
        self.assertIn('previous', response_json)

    def test_create_noun(self):
        """Assert "create" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.user)
        arn = util_helper.generate_dummy_arn()
        name = _faker.sentence()
        response = client.create_account(
            data={
                'account_arn': arn,
                'name': name,
                'resourcetype': 'AwsAccount',
            }
        )
        self.assertEqual(response.status_code, http.HTTPStatus.CREATED)
        response_json = response.json()
        self.assertEqual(response_json['account_arn'], arn)
        self.assertEqual(response_json['name'], name)
        self.assertEqual(response_json['user_id'], self.user.id)

    def test_get_noun(self):
        """Assert "get" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.user)
        account = helper.generate_aws_account(user=self.user)
        response = client.get_account(account.id)
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        response_json = response.json()
        self.assertEqual(response_json['id'], account.id)

    def test_invalid_request(self):
        """Assert invalid requests raise AttributeError."""
        client = helper.SandboxedRestClient()
        with self.assertRaises(AttributeError):
            client.foo_bar()

    def test_action_noun_verb_detail(self):
        """Assert "detail" requests work."""
        client = helper.SandboxedRestClient()
        client._force_authenticate(self.superuser)

        image = helper.generate_aws_image(
            status=AwsMachineImage.INSPECTED
        )
        response = client.post_image(
            noun_id=image.id,
            detail='reinspect'
        )
        self.assertEqual(response.status_code, http.HTTPStatus.OK)
        self.assertEqual(AwsMachineImage.PENDING, response.data['status'])


class GenerateAwsAccountTest(TestCase):
    """generate_aws_account tests."""

    def test_generate_aws_account_default(self):
        """Assert generation of an AwsAccount with default/no args."""
        account = helper.generate_aws_account()
        self.assertIsInstance(account, AwsAccount)
        self.assertIsNotNone(
            re.match(r'\d{1,12}', str(account.aws_account_id))
        )

    def test_generate_aws_account_with_args(self):
        """Assert generation of an AwsAccount with all specified args."""
        aws_account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id=aws_account_id)
        user = util_helper.generate_test_user()
        name = _faker.name()
        created_at = util_helper.utc_dt(2017, 1, 1, 0, 0, 0)
        account = helper.generate_aws_account(
            arn, aws_account_id, user, name, created_at
        )
        self.assertIsInstance(account, AwsAccount)
        self.assertEqual(account.account_arn, arn)
        self.assertEqual(account.aws_account_id, aws_account_id)
        self.assertEqual(account.user, user)
        self.assertEqual(account.name, name)
        self.assertEqual(account.created_at, created_at)


class GenerateAwsInstanceTest(TestCase):
    """generate_aws_instance test case."""

    def test_generate_aws_instance_default(self):
        """Assert generation of an AwsInstance with minimal args."""
        account = helper.generate_aws_account()
        instance = helper.generate_aws_instance(account)
        self.assertIsInstance(instance, AwsInstance)
        self.assertEqual(instance.account, account)
        self.assertIsNotNone(instance.ec2_instance_id)
        self.assertGreater(len(instance.ec2_instance_id), 0)
        self.assertIsNotNone(instance.region)
        self.assertGreater(len(instance.region), 0)

    def test_generate_aws_instance_with_args(self):
        """Assert generation of an AwsInstance with all specified args."""
        account = helper.generate_aws_account()
        ec2_instance_id = util_helper.generate_dummy_instance_id()
        region = util_helper.get_random_region()
        instance = helper.generate_aws_instance(
            account,
            ec2_instance_id=ec2_instance_id,
            region=region,
        )
        self.assertIsInstance(instance, AwsInstance)
        self.assertEqual(instance.account, account)
        self.assertEqual(instance.ec2_instance_id, ec2_instance_id)
        self.assertEqual(instance.region, region)


class GenerateAwsInstanceEventsTest(TestCase):
    """generate_aws_instance_events test case."""

    def test_generate_aws_events_default_and_no_times(self):
        """Assert generation of InstanceEvents with minimal args."""
        account = helper.generate_aws_account()
        instance = helper.generate_aws_instance(account)
        events = helper.generate_aws_instance_events(instance, tuple())
        self.assertEqual(len(events), 0)

    def test_generate_aws_events_with_some_times(self):
        """Assert generation of InstanceEvents with some times."""
        account = helper.generate_aws_account()
        instance = helper.generate_aws_instance(account)
        powered_times = (
            (None, util_helper.utc_dt(2017, 1, 1)),
            (util_helper.utc_dt(2017, 1, 2), util_helper.utc_dt(2017, 1, 3)),
            (util_helper.utc_dt(2017, 1, 4), None),
        )
        events = helper.generate_aws_instance_events(instance, powered_times)

        self.assertEqual(len(events), 4)
        self.assertEqual(events[0].occurred_at, powered_times[0][1])
        self.assertEqual(events[1].occurred_at, powered_times[1][0])
        self.assertEqual(events[2].occurred_at, powered_times[1][1])
        self.assertEqual(events[3].occurred_at, powered_times[2][0])

        self.assertEqual(events[0].event_type, InstanceEvent.TYPE.power_off)
        self.assertEqual(events[1].event_type, InstanceEvent.TYPE.power_on)
        self.assertEqual(events[2].event_type, InstanceEvent.TYPE.power_off)
        self.assertEqual(events[3].event_type, InstanceEvent.TYPE.power_on)

        # power_off events typically don't have an image defined, and the
        # first event here should be power_off.
        self.assertIsNone(events[0].machineimage)
        self.assertIsNotNone(events[0].instance_type)
        self.assertIsNotNone(events[0].subnet)

        # Assert they all have the same AMI, subnet, and instance type.
        for event in events[1:]:
            self.assertEqual(event.instance_type, events[0].instance_type)
            self.assertEqual(event.subnet, events[0].subnet)
            if event.event_type != event.TYPE.power_off:
                # power_off events typically don't have an image defined.
                # the second event should be power_on and should have an
                # image defined we can compare with.
                self.assertEqual(event.machineimage, events[1].machineimage)

    def test_generate_aws_events_with_args_and_some_times(self):
        """Assert generation of InstanceEvents with all specified args."""
        account = helper.generate_aws_account()
        instance = helper.generate_aws_instance(account)
        powered_times = (
            (None, util_helper.utc_dt(2017, 1, 1)),
            (util_helper.utc_dt(2017, 1, 2), util_helper.utc_dt(2017, 1, 3)),
            (util_helper.utc_dt(2017, 1, 4), None),
        )
        ec2_ami_id = util_helper.generate_dummy_image_id()
        instance_type = util_helper.get_random_instance_type()
        subnet = str(uuid.uuid4())
        events = helper.generate_aws_instance_events(
            instance,
            powered_times,
            ec2_ami_id=ec2_ami_id,
            instance_type=instance_type,
            subnet=subnet,
        )

        self.assertEqual(len(events), 4)
        # We don't care to check *everything* in the events since that should
        # already be covered by ``test_generate_events_with_some_times``.
        # Here we only care that argument values were set correctly.
        for event in events:
            if event.event_type != event.TYPE.power_off:
                self.assertEqual(event.machineimage.ec2_ami_id, ec2_ami_id)
            self.assertEqual(event.instance_type, instance_type)
            self.assertEqual(event.subnet, subnet)

    def test_generate_aws_events_with_no_image(self):
        """Assert generation of InstanceEvents with no_image specified."""
        account = helper.generate_aws_account()
        instance = helper.generate_aws_instance(account)
        powered_times = (
            (util_helper.utc_dt(2017, 1, 2), util_helper.utc_dt(2017, 1, 3)),
        )
        events = helper.generate_aws_instance_events(instance, powered_times,
                                                     no_image=True)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].occurred_at, powered_times[0][0])
        self.assertEqual(events[1].occurred_at, powered_times[0][1])
        self.assertIsNone(events[0].machineimage)
        self.assertIsNotNone(events[0].instance_type)
        self.assertIsNotNone(events[0].subnet)

        # Assert they all have the same subnet and instance type but no image.
        for event in events:
            self.assertIsNone(event.machineimage)
            self.assertEqual(event.instance_type, events[0].instance_type)
            self.assertEqual(event.subnet, events[0].subnet)


class GenerateAwsImageTest(TestCase):
    """generate_aws_image test case."""

    def test_generate_aws_image_default(self):
        """Assert generation of an AwsMachineImage with minimal args."""
        image = helper.generate_aws_image()
        self.assertIsInstance(image.owner_aws_account_id, Decimal)
        self.assertEqual(image.platform, image.NONE)
        self.assertIsNotNone(image.ec2_ami_id)
        self.assertGreater(len(image.ec2_ami_id), 0)
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertIsNone(image.name)
        self.assertFalse(image.rhel_challenged)
        self.assertFalse(image.openshift_challenged)
        self.assertFalse(image.is_cloud_access)
        self.assertFalse(image.is_marketplace)

    def test_generate_aws_image_with_args(self):
        """Assert generation of an AwsMachineImage with all specified args."""
        account_id = util_helper.generate_dummy_aws_account_id()
        ec2_ami_id = util_helper.generate_dummy_image_id()
        name = _faker.name()

        image = helper.generate_aws_image(
            account_id,
            is_encrypted=True,
            is_windows=True,
            ec2_ami_id=ec2_ami_id,
            rhel_detected=True,
            openshift_detected=True,
            name=name,
            status=AwsMachineImage.PREPARING,
            rhel_challenged=True,
            openshift_challenged=True
        )

        self.assertIsInstance(image, AwsMachineImage)
        self.assertEqual(image.owner_aws_account_id, account_id)
        self.assertEqual(image.platform, image.WINDOWS)
        self.assertEqual(image.ec2_ami_id, ec2_ami_id)
        self.assertTrue(image.rhel_detected)
        self.assertTrue(image.openshift_detected)
        self.assertEqual(image.name, name)
        self.assertEqual(image.status, AwsMachineImage.PREPARING)
        self.assertTrue(image.rhel_challenged)
        self.assertTrue(image.openshift_challenged)
        self.assertFalse(image.is_cloud_access)
        self.assertFalse(image.is_marketplace)

    def test_generate_aws_image_with_is_cloud_access(self):
        """Assert generation of an AwsMachineImage with is_cloud_access."""
        account_id = util_helper.generate_dummy_aws_account_id()
        name = _faker.name()

        image = helper.generate_aws_image(
            account_id,
            name=name,
            is_cloud_access=True,
        )

        self.assertNotEqual(image.owner_aws_account_id, account_id)
        self.assertIn(image.owner_aws_account_id,
                      settings.RHEL_IMAGES_AWS_ACCOUNTS)
        self.assertTrue(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertNotEqual(image.name, name)
        self.assertIn(CLOUD_ACCESS_NAME_TOKEN, image.name)
        self.assertTrue(image.is_cloud_access)
        self.assertFalse(image.is_marketplace)

    def test_generate_aws_image_with_is_marketplace(self):
        """Assert generation of an AwsMachineImage with is_marketplace."""
        account_id = util_helper.generate_dummy_aws_account_id()
        name = _faker.name()

        image = helper.generate_aws_image(
            account_id,
            name=name,
            is_marketplace=True,
        )

        self.assertNotEqual(image.owner_aws_account_id, account_id)
        self.assertIn(image.owner_aws_account_id,
                      settings.RHEL_IMAGES_AWS_ACCOUNTS)
        self.assertFalse(image.rhel_detected)
        self.assertFalse(image.openshift_detected)
        self.assertNotEqual(image.name, name)
        self.assertIn(MARKETPLACE_NAME_TOKEN, image.name)
        self.assertFalse(image.is_cloud_access)
        self.assertTrue(image.is_marketplace)


class GenerateAwsEc2InstanceDefinitionsTest(TestCase):
    """generate_aws_ec2_definitions test case."""

    def test_generate_aws_ec2_definitions_when_empty(self):
        """Assert generation of AWS EC2 instance definitions."""
        self.assertEqual(AwsEC2InstanceDefinitions.objects.count(), 0)
        helper.generate_aws_ec2_definitions()
        self.assertEqual(
            AwsEC2InstanceDefinitions.objects.count(),
            len(util_helper.SOME_EC2_INSTANCE_TYPES),
        )

    @patch.object(helper, 'logger')
    def test_generate_aws_ec2_definitions_warns_when_not_empty(
        self, mock_logger
    ):
        """Assert warning when generating definition that already exists."""
        helper.generate_aws_ec2_definitions()
        helper.generate_aws_ec2_definitions()
        self.assertEqual(
            AwsEC2InstanceDefinitions.objects.count(),
            len(util_helper.SOME_EC2_INSTANCE_TYPES),
        )
        # warning counts should match because each type was attempted twice.
        self.assertEqual(
            len(mock_logger.warning.mock_calls),
            len(util_helper.SOME_EC2_INSTANCE_TYPES),
        )
