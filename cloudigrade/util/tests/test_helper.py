"""Collection of tests for ``util.tests.helper`` module.

Because even test helpers should be tested!
"""
import datetime
import random
import uuid

from django.test import TestCase

from util import aws
from util.tests import helper


class UtilHelperTest(TestCase):
    """Test helper functions test case."""

    def test_generate_dummy_aws_account_id(self):
        """Assert generation of an appropriate AWS Account ID."""
        account_id = helper.generate_dummy_aws_account_id()
        self.assertLess(account_id, helper.MAX_AWS_ACCOUNT_ID)
        self.assertGreater(account_id, 0)

    def test_generate_dummy_arn_random_account_id(self):
        """Assert generation of an ARN without a specified account ID."""
        arn = helper.generate_dummy_arn()
        account_id = aws.extract_account_id_from_arn(arn)
        self.assertIn(str(account_id), arn)

    def test_generate_dummy_arn_given_account_id(self):
        """Assert generation of an ARN with a specified account ID."""
        account_id = 123456789
        arn = helper.generate_dummy_arn(account_id)
        self.assertIn(str(account_id), arn)

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
        image_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        subnet_id = str(uuid.uuid4())
        state = aws.InstanceState.shutting_down
        instance_type = random.choice(helper.SOME_EC2_INSTANCE_TYPES)
        instance = helper.generate_dummy_describe_instance(
            instance_id, image_id, subnet_id, state, instance_type
        )
        self.assertEqual(instance['ImageId'], image_id)
        self.assertEqual(instance['InstanceId'], instance_id)
        self.assertEqual(instance['InstanceType'], instance_type)
        self.assertEqual(instance['SubnetId'], subnet_id)
        self.assertEqual(instance['State']['Code'], state.value)
        self.assertEqual(instance['State']['Name'], state.name)

    def test_generate_mock_ec2_instance_default(self):
        """Assert generated instance has values where expected."""
        instance = helper.generate_mock_ec2_instance()
        self.assertIsNotNone(instance.image_id)
        self.assertIsNotNone(instance.instance_id)
        self.assertIsNotNone(instance.instance_type)
        self.assertIsNotNone(instance.subnet_id)
        self.assertIsNotNone(instance.state)
        self.assertIsNotNone(instance.state['Code'])
        self.assertIsNotNone(instance.state['Name'])

    def test_generate_mock_ec2_instance_with_values(self):
        """Assert generated instance contains given values."""
        image_id = str(uuid.uuid4())
        instance_id = str(uuid.uuid4())
        subnet_id = str(uuid.uuid4())
        state = aws.InstanceState.shutting_down
        instance_type = random.choice(helper.SOME_EC2_INSTANCE_TYPES)
        instance = helper.generate_mock_ec2_instance(
            instance_id, image_id, subnet_id, state, instance_type
        )
        self.assertEqual(instance.image_id, image_id)
        self.assertEqual(instance.instance_id, instance_id)
        self.assertEqual(instance.instance_type, instance_type)
        self.assertEqual(instance.subnet_id, subnet_id)
        self.assertEqual(instance.state['Code'], state.value)
        self.assertEqual(instance.state['Name'], state.name)

    def test_utc_dt(self):
        """Assert utc_dt adds timezone info."""
        d_no_tz = datetime.datetime(2018, 1, 1)
        d_helped = helper.utc_dt(2018, 1, 1)
        self.assertNotEqual(d_helped, d_no_tz)
        self.assertIsNotNone(d_helped.tzinfo)
