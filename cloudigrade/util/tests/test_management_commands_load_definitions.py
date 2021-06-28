"""Collection of tests for the 'load_definitions' management command."""
import random
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from api.models import InstanceDefinition
from util.tests import helper


class LoadDefinitionsTest(TestCase):
    """Management command 'load_definitions' test case."""

    def create_random_definition(self):
        """Create and save a random definition."""
        InstanceDefinition.objects.create(
            instance_type=helper.get_random_instance_type(),
            memory_mib=random.randrange(4),
            vcpu=random.randrange(4),
            json_definition='{"test": "data"}',
            cloud_type="aws",
        )
        InstanceDefinition.objects.create(
            instance_type=helper.get_random_instance_type(),
            memory_mib=random.randrange(4),
            vcpu=random.randrange(4),
            json_definition='{"test": "data"}',
            cloud_type="azure",
        )

    def test_skip_when_any_present(self):
        """Test that 'load_definitions' skips task if definitions exist."""
        self.create_random_definition()
        _path = "util.management.commands.load_definitions"
        with patch("{}.aws_tasks".format(_path)) as mock_aws_tasks:
            with patch("{}.azure_tasks".format(_path)) as mock_azure_tasks:
                call_command("load_definitions")
                aws_task = mock_aws_tasks.repopulate_ec2_instance_mapping
                azure_task = mock_azure_tasks.repopulate_azure_instance_mapping

                aws_task.delay.assert_not_called()
                azure_task.delay.assert_not_called()

    def test_load_when_none(self):
        """Test that 'load_definitions' runs task if no definitions exist."""
        _path = "util.management.commands.load_definitions"
        with patch("{}.aws_tasks".format(_path)) as mock_aws_tasks:
            with patch("{}.azure_tasks".format(_path)) as mock_azure_tasks:
                call_command("load_definitions")
                aws_task = mock_aws_tasks.repopulate_ec2_instance_mapping
                azure_task = mock_azure_tasks.repopulate_azure_instance_mapping

                aws_task.delay.assert_called()
                azure_task.delay.assert_called()

    def test_skip_when_any_present_but_forced(self):
        """Test force-calling 'load_definitions' when definitions exist."""
        self.create_random_definition()
        _path = "util.management.commands.load_definitions"
        with patch("{}.aws_tasks".format(_path)) as mock_aws_tasks:
            with patch("{}.azure_tasks".format(_path)) as mock_azure_tasks:
                call_command("load_definitions", force=True)
                aws_task = mock_aws_tasks.repopulate_ec2_instance_mapping
                azure_task = mock_azure_tasks.repopulate_azure_instance_mapping

                aws_task.delay.assert_called()
                azure_task.delay.assert_called()
