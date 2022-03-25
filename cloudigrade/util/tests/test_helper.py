"""Collection of tests for ``util.tests.helper`` module.

Because even test helpers should be tested!
"""
import datetime
import random
import re
import string

import faker
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.test import TestCase

from util import aws
from util.tests import helper

_faker = faker.Faker()


class UtilHelperTest(TestCase):
    """Test helper functions test case."""

    def test_generate_dummy_aws_account_id(self):
        """Assert generation of an appropriate AWS AwsAccount ID."""
        account_id = str(helper.generate_dummy_aws_account_id())
        self.assertIsNotNone(re.match(r"\d{1,12}", account_id))

    def test_generate_dummy_arn_random_account_id(self):
        """Assert generation of an ARN without a specified account ID."""
        arn = helper.generate_dummy_arn()
        account_id = aws.AwsArn(arn).account_id
        self.assertIn(str(account_id), arn)

    def test_generate_dummy_arn_given_account_id(self):
        """Assert generation of an ARN with a specified account ID."""
        account_id = "012345678901"
        arn = helper.generate_dummy_arn(account_id)
        self.assertIn(account_id, arn)

    def test_generate_dummy_arn_given_resource(self):
        """Assert generation of an ARN with a specified resource."""
        resource = _faker.slug()
        arn = helper.generate_dummy_arn(resource=resource)
        self.assertTrue(arn.endswith(resource))

    @helper.clouditardis(helper.utc_dt(2020, 1, 2, 3, 4, 5))
    def test_generate_dummy_block_device_mapping_default(self):
        """Assert generated block device mapping has values where expected."""
        device_mapping = helper.generate_dummy_block_device_mapping()
        self.assertIsNotNone(device_mapping["DeviceName"])
        self.assertTrue(device_mapping["DeviceName"].startswith("/dev/"))
        self.assertIsNotNone(device_mapping["Ebs"])
        self.assertEqual(
            device_mapping["Ebs"]["AttachTime"], "2020-01-02T03:04:05+00:00"
        )
        self.assertTrue(device_mapping["Ebs"]["DeleteOnTermination"])
        self.assertEqual(device_mapping["Ebs"]["Status"], "attached")
        self.assertIsNotNone(device_mapping["Ebs"]["VolumeId"])
        self.assertTrue(device_mapping["Ebs"]["VolumeId"].startswith("vol-"))

    def test_generate_dummy_block_device_mapping_with_values(self):
        """Assert generated block device mapping contains given values."""
        device_name = "/dev/potato"
        device_type = "gem"
        attach_time = "2020-10-08T16:16:16+00:00"
        delete_on_termination = False
        status = "delicious"
        volume_id = "vol-taters"
        device_mapping = helper.generate_dummy_block_device_mapping(
            device_name=device_name,
            device_type=device_type,
            attach_time=attach_time,
            delete_on_termination=delete_on_termination,
            status=status,
            volume_id=volume_id,
        )
        self.assertEqual(device_mapping["DeviceName"], device_name)
        self.assertIn(device_type, device_mapping)
        self.assertEqual(device_mapping[device_type]["AttachTime"], attach_time)
        self.assertFalse(device_mapping[device_type]["DeleteOnTermination"])
        self.assertEqual(device_mapping[device_type]["Status"], status)
        self.assertEqual(device_mapping[device_type]["VolumeId"], volume_id)

    def test_generate_dummy_describe_instance_default(self):
        """Assert generated instance has values where expected."""
        instance = helper.generate_dummy_describe_instance()
        self.assertIsNotNone(instance["ImageId"])
        self.assertIsNotNone(instance["InstanceId"])
        self.assertIsNotNone(instance["InstanceType"])
        self.assertIsNotNone(instance["SubnetId"])
        self.assertIsNotNone(instance["State"])
        self.assertIsNotNone(instance["State"]["Code"])
        self.assertIsNotNone(instance["State"]["Name"])
        self.assertEqual(len(instance["BlockDeviceMappings"]), 2)

    def test_generate_dummy_describe_instance_with_values(self):
        """Assert generated instance contains given values."""
        image_id = helper.generate_dummy_image_id()
        instance_id = helper.generate_dummy_instance_id()
        subnet_id = helper.generate_dummy_subnet_id()
        state = aws.InstanceState.shutting_down
        instance_type = helper.get_random_instance_type()
        device_mapping = helper.generate_dummy_block_device_mapping()
        instance = helper.generate_dummy_describe_instance(
            instance_id=instance_id,
            image_id=image_id,
            subnet_id=subnet_id,
            state=state,
            instance_type=instance_type,
            device_mappings=[device_mapping],
        )
        self.assertEqual(instance["ImageId"], image_id)
        self.assertEqual(instance["InstanceId"], instance_id)
        self.assertEqual(instance["InstanceType"], instance_type)
        self.assertEqual(instance["SubnetId"], subnet_id)
        self.assertEqual(instance["State"]["Code"], state.value)
        self.assertEqual(instance["State"]["Name"], state.name)
        self.assertEqual(instance["State"]["Name"], state.name)
        self.assertEqual(instance["BlockDeviceMappings"], [device_mapping])

    def test_generate_dummy_describe_instance_no_subnet(self):
        """Assert generated instance has no SubnetId key if no_subnet is True."""
        instance = helper.generate_dummy_describe_instance(no_subnet=True)
        self.assertNotIn("SubnetId", instance)

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
        hex_part = snapshot_id.split("snap-")[1]

        self.assertIn("snap-", snapshot_id)
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
        self.assertTrue(volume_id.startswith("vol-"))
        self.assertEqual(len(volume_id), 21)

    def test_generate_dummy_image_id(self):
        """Assert generation of an appropriate image ID."""
        volume_id = helper.generate_dummy_image_id()
        self.assertTrue(volume_id.startswith("ami-"))
        self.assertEqual(len(volume_id), 12)

    def test_generate_dummy_instance_id(self):
        """Assert generation of an appropriate EC2 instance ID."""
        volume_id = helper.generate_dummy_instance_id()
        self.assertTrue(volume_id.startswith("i-"))
        self.assertEqual(len(volume_id), 19)

    def test_generate_dummy_subnet_id(self):
        """Assert generation of an appropriate EC2 subnet ID."""
        volume_id = helper.generate_dummy_subnet_id()
        self.assertTrue(volume_id.startswith("subnet-"))
        self.assertEqual(len(volume_id), 15)

    def test_generate_test_user(self):
        """Assert generation of test user with appropriate defaults."""
        user = helper.generate_test_user()
        self.assertFalse(user.is_superuser)
        other_user = helper.generate_test_user()
        self.assertNotEqual(user, other_user)
        self.assertNotEqual(user.username, other_user.username)

    def test_generate_test_user_with_args(self):
        """Assert generation of test user with specified arguments."""
        account_number = _faker.random_int(min=100000, max=999999)
        date_joined = helper.utc_dt(2017, 12, 11, 8, 0, 0)
        user = helper.generate_test_user(
            account_number=account_number, is_superuser=True, date_joined=date_joined
        )
        self.assertEqual(user.username, account_number)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.date_joined, date_joined)

    def test_get_test_user_creates(self):
        """Assert get_test_user creates a user when it doesn't yet exist."""
        user = helper.get_test_user()
        self.assertIsNotNone(user)

    def test_get_test_user_updates_without_password(self):
        """Assert get_test_user gets and updates user if found."""
        account_number = _faker.random_int(min=100000, max=999999)
        original_user = User.objects.create_user(account_number)
        user = helper.get_test_user(account_number, is_superuser=True)
        original_user.refresh_from_db()
        self.assertEqual(user, original_user)
        self.assertTrue(user.is_superuser)

    def test_get_test_user_updates_with_password(self):
        """Assert get_test_user updates user with password if found."""
        account_number = _faker.random_int(min=100000, max=999999)
        password = _faker.uuid4()
        original_user = User.objects.create_user(account_number)
        user = helper.get_test_user(account_number, password)
        original_user.refresh_from_db()
        self.assertEqual(user, original_user)
        self.assertTrue(user.check_password(password))

    def test_clouditardis(self):
        """Assert that clouditardis breaks the space-time continuum."""
        the_present_time = datetime.datetime.now(datetime.timezone.utc)
        the_present_date = the_present_time.date()

        the_day_i_invented_time_travel = helper.utc_dt(1955, 11, 5, 4, 29)
        with helper.clouditardis(the_day_i_invented_time_travel):
            # local imports to simulate tests
            from util.misc import get_now as _get_now, get_today as _get_today

            the_past_time = _get_now()
            the_past_date = _get_today()

        self.assertLess(the_past_time, the_present_time)
        self.assertLess(the_past_date, the_present_date)

    def test_generate_dummy_azure_instance_id(self):
        """Assert generation of an appropriate Azure Instance ID."""
        instance_id = str(helper.generate_dummy_azure_instance_id())
        self.assertIsNotNone(
            re.fullmatch(
                r"\/subscriptions\/[\w\-]*\/resourceGroups\/[\w]*\/providers"
                r"\/Microsoft.Compute\/virtualMachines/[\w]*",
                instance_id,
            )
        )

    def test_generate_dummy_azure_image_id(self):
        """Assert generation of an appropriate Azure Image ID."""
        instance_id = str(helper.generate_dummy_azure_image_id())
        self.assertIsNotNone(
            re.fullmatch(
                r"\/subscriptions\/[\w\-]*\/resourceGroups\/[\w]*\/providers"
                r"\/Microsoft.Compute\/images/[\w]*",
                instance_id,
            )
        )

    def test_mock_signal_handler(self):
        """Assert mock_signal_handler temporarily bypasses original signal handler."""

        class OriginalHandlerWasCalled(Exception):
            """Raise to identify when the original signal handler is called."""

        @receiver(post_save, sender=User)
        def _handler(*args, **kwargs):
            """Raise exception to indicate the handler was called."""
            raise OriginalHandlerWasCalled

        with helper.mock_signal_handler(post_save, _handler, User) as mock_handler:
            # OriginalHandlerWasCalled should not be raised because _handler is mocked.
            User.objects.create_user(_faker.name())
            mock_handler.assert_called_once()

        with self.assertRaises(OriginalHandlerWasCalled):
            User.objects.create_user(_faker.name())
