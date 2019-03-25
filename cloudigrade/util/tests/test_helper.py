"""Collection of tests for ``util.tests.helper`` module.

Because even test helpers should be tested!
"""
import datetime
import random
import re
import string
import uuid

import faker
from django.contrib.auth.models import User
from django.test import TestCase

from util import aws
from util.tests import helper

_faker = faker.Faker()


class UtilHelperTest(TestCase):
    """Test helper functions test case."""

    def test_generate_dummy_aws_account_id(self):
        """Assert generation of an appropriate AWS AwsAccount ID."""
        account_id = str(helper.generate_dummy_aws_account_id())
        self.assertIsNotNone(re.match(r'\d{1,12}', account_id))

    def test_generate_dummy_arn_random_account_id(self):
        """Assert generation of an ARN without a specified account ID."""
        arn = helper.generate_dummy_arn()
        account_id = aws.AwsArn(arn).account_id
        self.assertIn(str(account_id), arn)

    def test_generate_dummy_arn_given_account_id(self):
        """Assert generation of an ARN with a specified account ID."""
        account_id = '012345678901'
        arn = helper.generate_dummy_arn(account_id)
        self.assertIn(account_id, arn)

    def test_generate_dummy_arn_given_resource(self):
        """Assert generation of an ARN with a specified resource."""
        resource = _faker.slug()
        arn = helper.generate_dummy_arn(resource=resource)
        self.assertTrue(arn.endswith(resource))

    def test_generate_dummy_describe_instance_default(self):
        """Assert generated instance has values where expected."""
        instance = helper.generate_dummy_describe_instance()
        self.assertIsNotNone(instance['ImageId'])
        self.assertIsNotNone(instance['InstanceId'])
        self.assertIsNotNone(instance['InstanceType'])
        self.assertIsNotNone(instance['SubnetId'])
        self.assertIsNotNone(instance['State'])
        self.assertIsNotNone(instance['State']['Code'])
        self.assertIsNotNone(instance['State']['Name'])

    def test_generate_dummy_describe_instance_with_values(self):
        """Assert generated instance contains given values."""
        image_id = helper.generate_dummy_image_id()
        instance_id = helper.generate_dummy_instance_id()
        subnet_id = helper.generate_dummy_subnet_id()
        state = aws.InstanceState.shutting_down
        instance_type = helper.get_random_instance_type()
        instance = helper.generate_dummy_describe_instance(
            instance_id, image_id, subnet_id, state, instance_type
        )
        self.assertEqual(instance['ImageId'], image_id)
        self.assertEqual(instance['InstanceId'], instance_id)
        self.assertEqual(instance['InstanceType'], instance_type)
        self.assertEqual(instance['SubnetId'], subnet_id)
        self.assertEqual(instance['State']['Code'], state.value)
        self.assertEqual(instance['State']['Name'], state.name)

    def test_generate_mock_image(self):
        """Assert generated image contains given value."""
        image_id = helper.generate_dummy_image_id()
        encrypted = random.choice((True, False))
        image = helper.generate_mock_image(image_id, encrypted)

        self.assertEqual(image.image_id, image_id)
        self.assertIsNotNone(image.root_device_name)
        self.assertIsNotNone(image.root_device_type)
        self.assertIsInstance(image.block_device_mappings, list)
        self.assertIsInstance(image.block_device_mappings[0], dict)

    def test_generate_dummy_snapshot_id(self):
        """Assert generated id has the appropriate format."""
        snapshot_id = helper.generate_dummy_snapshot_id()
        hex_part = snapshot_id.split('snap-')[1]

        self.assertIn('snap-', snapshot_id)
        self.assertEqual(len(hex_part), 17)
        for digit in hex_part:
            self.assertIn(digit, string.hexdigits)

    def test_generate_mock_snapshot_defaults(self):
        """Assert snapshots are created without provided values."""
        snapshot = helper.generate_mock_snapshot()
        self.assertIsNotNone(snapshot.snapshot_id)
        self.assertIsNotNone(snapshot.encrypted)

    def test_generate_mock_snapshot_id_included(self):
        """Assert snapshots are created with provided id."""
        snapshot_id = helper.generate_dummy_snapshot_id()
        snapshot = helper.generate_mock_snapshot(snapshot_id)
        self.assertEqual(snapshot.snapshot_id, snapshot_id)

    def test_generate_mock_snapshot_id_encrypted(self):
        """Assert created snapshots obey the encrypted arg."""
        snapshot = helper.generate_mock_snapshot(encrypted=True)
        self.assertTrue(snapshot.encrypted)

    def test_utc_dt(self):
        """Assert utc_dt adds timezone info."""
        d_no_tz = datetime.datetime(2018, 1, 1)
        d_helped = helper.utc_dt(2018, 1, 1)
        self.assertNotEqual(d_helped, d_no_tz)
        self.assertIsNotNone(d_helped.tzinfo)

    def test_generate_dummy_availability_zone(self):
        """Assert generation of an appropriate availability zone."""
        zone = helper.generate_dummy_availability_zone()
        self.assertIn(zone[:-1], helper.SOME_AWS_REGIONS)

    def test_generate_dummy_availability_zone_with_region(self):
        """Assert region is used to generate availability zone."""
        region = helper.get_random_region()
        zone = helper.generate_dummy_availability_zone(region)
        self.assertEqual(zone[:-1], region)

    def test_generate_dummy_volume_id(self):
        """Assert generation of an appropriate volume ID."""
        volume_id = helper.generate_dummy_volume_id()
        self.assertTrue(volume_id.startswith('vol-'))
        self.assertEqual(len(volume_id), 21)

    def test_generate_dummy_image_id(self):
        """Assert generation of an appropriate image ID."""
        volume_id = helper.generate_dummy_image_id()
        self.assertTrue(volume_id.startswith('ami-'))
        self.assertEqual(len(volume_id), 12)

    def test_generate_dummy_instance_id(self):
        """Assert generation of an appropriate EC2 instance ID."""
        volume_id = helper.generate_dummy_instance_id()
        self.assertTrue(volume_id.startswith('i-'))
        self.assertEqual(len(volume_id), 19)

    def test_generate_dummy_subnet_id(self):
        """Assert generation of an appropriate EC2 subnet ID."""
        volume_id = helper.generate_dummy_subnet_id()
        self.assertTrue(volume_id.startswith('subnet-'))
        self.assertEqual(len(volume_id), 15)

    def test_generate_test_user(self):
        """Assert generation of test user with appropriate defaults."""
        user = helper.generate_test_user()
        self.assertEqual(user.email, user.username)
        self.assertTrue(user.email.endswith('@mail.127.0.0.1.nip.io'))
        self.assertFalse(user.is_superuser)
        other_user = helper.generate_test_user()
        self.assertNotEqual(user, other_user)
        self.assertNotEqual(user.username, other_user.username)

    def test_generate_test_user_with_args(self):
        """Assert generation of test user with specified arguments."""
        email = f'{uuid.uuid4()}@example.com'
        user = helper.generate_test_user(email=email, is_superuser=True)
        self.assertEqual(user.email, email)
        self.assertEqual(user.username, email)
        self.assertTrue(user.is_superuser)

    def test_generate_mock_image_dict(self):
        """Assert generation of an image-like dict."""
        image_dict = helper.generate_mock_image_dict()
        self.assertIn('ImageId', image_dict)

    def test_generate_mock_image_dict_with_args(self):
        """Assert generation of an image-like dict with specified arguments."""
        image_id = helper.generate_dummy_image_id()
        image_dict = helper.generate_mock_image_dict(image_id)
        self.assertEqual(image_dict['ImageId'], image_id)

    def test_get_test_user_creates(self):
        """Assert get_test_user creates a user when it doesn't yet exist."""
        user = helper.get_test_user()
        self.assertIsNotNone(user)

    def test_get_test_user_updates_without_password(self):
        """Assert get_test_user gets and updates user if found."""
        email = f'{_faker.slug()}@example.com'
        original_user = User.objects.create_user(email)
        user = helper.get_test_user(email, is_superuser=True)
        original_user.refresh_from_db()
        self.assertEqual(user, original_user)
        self.assertTrue(user.is_superuser)

    def test_get_test_user_updates_with_password(self):
        """Assert get_test_user updates user with password if found."""
        email = f'{_faker.slug()}@example.com'
        password = _faker.uuid4()
        original_user = User.objects.create_user(email)
        user = helper.get_test_user(email, password)
        original_user.refresh_from_db()
        self.assertEqual(user, original_user)
        self.assertTrue(user.check_password(password))
