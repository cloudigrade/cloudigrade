"""Collection of tests for ``account.tests.helper`` module.

Because even test helpers should be tested!
"""
import random
import re
import uuid
from decimal import Decimal

import faker
from django.conf import settings
from django.test import TestCase

from account.models import (AwsAccount, AwsInstance, AwsMachineImage,
                            CLOUD_ACCESS_NAME_TOKEN, InstanceEvent,
                            MARKETPLACE_NAME_TOKEN)
from account.tests import helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class GenerateAwsAccountTest(TestCase):
    """generate_aws_account tests."""

    def test_generate_aws_account_default(self):
        """Assert generation of an AwsAccount with default/no args."""
        account = helper.generate_aws_account()
        self.assertIsInstance(account, AwsAccount)
        self.assertIsNotNone(re.match(r'\d{1,12}', account.aws_account_id))

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
        self.assertEqual(account.aws_account_id, str(aws_account_id))
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
        region = random.choice(util_helper.SOME_AWS_REGIONS)
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
        instance_type = random.choice(tuple(
            util_helper.SOME_EC2_INSTANCE_TYPES.keys()
        ))
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
        name = 'Taters'

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
        name = 'Taters'

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
        name = 'Taters'

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
