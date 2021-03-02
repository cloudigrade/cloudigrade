"""Collection of tests for the 'loadec2definitions' management command."""
import random
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from api.models import InstanceDefinition
from util.tests import helper


class LoadEc2DefinitionsTest(TestCase):
    """Management command 'loadec2definitions' test case."""

    def create_random_definition(self):
        """Create and save a random definition."""
        InstanceDefinition.objects.create(
            instance_type=helper.get_random_instance_type(),
            memory=random.randrange(4),
            vcpu=random.randrange(4),
            json_definition='{"test": "data"}',
            cloud_type="aws",
        )

    def test_skip_when_any_present(self):
        """Test that 'loadec2definitions' skips task if definitions exist."""
        self.create_random_definition()
        _path = "util.management.commands.loadec2definitions"
        with patch("{}.tasks".format(_path)) as mock_tasks:
            call_command("loadec2definitions")
            task = mock_tasks.repopulate_ec2_instance_mapping
            task.delay.assert_not_called()

    def test_load_when_none(self):
        """Test that 'loadec2definitions' runs task if no definitions exist."""
        _path = "util.management.commands.loadec2definitions"
        with patch("{}.tasks".format(_path)) as mock_tasks:
            call_command("loadec2definitions")
            task = mock_tasks.repopulate_ec2_instance_mapping
            task.delay.assert_called()

    def test_skip_when_any_present_but_forced(self):
        """Test force-calling 'loadec2definitions' when definitions exist."""
        self.create_random_definition()
        _path = "util.management.commands.loadec2definitions"
        with patch("{}.tasks".format(_path)) as mock_tasks:
            call_command("loadec2definitions", force=True)
            task = mock_tasks.repopulate_ec2_instance_mapping
            task.delay.assert_called()
