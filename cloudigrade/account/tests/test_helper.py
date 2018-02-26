"""Collection of tests for ``account.tests.helper`` module.

Because even test helpers should be tested!
"""
import datetime
import random
import uuid

from django.test import TestCase

from account.models import Account, Instance, InstanceEvent
from account.tests import helper
from util.tests import helper as util_helper


class AccountHelperTest(TestCase):
    """Test helper functions test case."""

    def test_generate_account_default(self):
        """Assert generation of an Account with default/no args."""
        account = helper.generate_account()
        self.assertIsInstance(account, Account)
        self.assertLess(account.account_id, util_helper.MAX_AWS_ACCOUNT_ID)
        self.assertGreater(account.account_id, 0)
        self.assertIn(str(account.account_id), account.account_arn)

    def test_generate_account_with_args(self):
        """Assert generation of an Account with all specified args."""
        account_id = util_helper.generate_dummy_aws_account_id()
        arn = util_helper.generate_dummy_arn(account_id)
        account = helper.generate_account(arn=arn, account_id=account_id)
        self.assertIsInstance(account, Account)
        self.assertEqual(account.account_arn, arn)
        self.assertEqual(account.account_id, account_id)

    def test_generate_instance_default(self):
        """Assert generation of an Instance with minimal args."""
        account = helper.generate_account()
        instance = helper.generate_instance(account)
        self.assertIsInstance(instance, Instance)
        self.assertEqual(instance.account, account)
        self.assertIsNotNone(instance.ec2_instance_id)
        self.assertGreater(len(instance.ec2_instance_id), 0)
        self.assertIsNotNone(instance.region)
        self.assertGreater(len(instance.region), 0)

    def test_generate_instance_with_args(self):
        """Assert generation of an Instance with all specified args."""
        account = helper.generate_account()
        ec2_instance_id = str(uuid.uuid4())
        region = str(uuid.uuid4())
        instance = helper.generate_instance(
            account,
            ec2_instance_id=ec2_instance_id,
            region=region
        )
        self.assertIsInstance(instance, Instance)
        self.assertEqual(instance.account, account)
        self.assertEqual(instance.ec2_instance_id, ec2_instance_id)
        self.assertEqual(instance.region, region)

    def test_generate_events_default_and_no_times(self):
        """Assert generation of InstanceEvents with minimal args."""
        account = helper.generate_account()
        instance = helper.generate_instance(account)
        events = helper.generate_instance_events(instance, tuple())
        self.assertEqual(len(events), 0)

    def test_generate_events_with_some_times(self):
        """Assert generation of InstanceEvents with some times."""
        account = helper.generate_account()
        instance = helper.generate_instance(account)
        powered_times = (
            (None, datetime.datetime(2017, 1, 1)),
            (datetime.datetime(2017, 1, 2), datetime.datetime(2017, 1, 3)),
            (datetime.datetime(2017, 1, 4), None),
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

        self.assertIsNotNone(events[0].ec2_ami_id)
        self.assertIsNotNone(events[0].instance_type)
        self.assertIsNotNone(events[0].subnet)

        # Assert they all have the same AMI, subnet, and instance type.
        for event in events[1:]:
            self.assertEqual(event.ec2_ami_id, events[0].ec2_ami_id)
            self.assertEqual(event.instance_type, events[0].instance_type)
            self.assertEqual(event.subnet, events[0].subnet)

    def test_generate_events_with_args_and_some_times(self):
        """Assert generation of InstanceEvents with all specified args."""
        account = helper.generate_account()
        instance = helper.generate_instance(account)
        powered_times = (
            (None, datetime.datetime(2017, 1, 1)),
            (datetime.datetime(2017, 1, 2), datetime.datetime(2017, 1, 3)),
            (datetime.datetime(2017, 1, 4), None),
        )
        ec2_ami_id = str(uuid.uuid4())
        instance_type = random.choice(util_helper.SOME_EC2_INSTANCE_TYPES)
        subnet = str(uuid.uuid4())
        events = helper.generate_instance_events(
            instance, powered_times,
            ec2_ami_id=ec2_ami_id,
            instance_type=instance_type,
            subnet=subnet
        )

        self.assertEqual(len(events), 4)
        # We don't care to check *everything* in the events since that should
        # already be covered by ``test_generate_events_with_some_times``.
        # Here we only care that argument values were set correctly.
        for event in events:
            self.assertEqual(event.ec2_ami_id, ec2_ami_id)
            self.assertEqual(event.instance_type, instance_type)
            self.assertEqual(event.subnet, subnet)
