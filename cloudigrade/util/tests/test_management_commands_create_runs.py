"""Collection of tests for the 'create_runs' management command."""
from unittest import skip
from unittest.mock import patch

import faker
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from api.models import ConcurrentUsage, Run
from api.tests import helper as api_helper
from util.tests import helper as util_helper


class CreateRunsTest(TestCase):
    """Management command 'create_runs' test case."""

    def setUp(self):
        """Set up test data."""
        self.user = util_helper.generate_test_user()
        self.account = api_helper.generate_aws_account(user=self.user)
        self.image_rhel = api_helper.generate_aws_image(rhel_detected=True)
        self.instance = api_helper.generate_aws_instance(
            self.account, image=self.image_rhel
        )
        self.instance_type = "c5.xlarge"  # 4 vcpu and 8.0 memory
        self.factory = APIRequestFactory()
        self.faker = faker.Faker()

        api_helper.generate_single_run(
            self.instance,
            (
                util_helper.utc_dt(2019, 3, 15, 1, 0, 0),
                util_helper.utc_dt(2019, 3, 15, 2, 0, 0),
            ),
            image=self.instance.machine_image,
            instance_type=self.instance_type,
        )

    def test_handle(self):
        """Test calling create_runs with confirm arg."""
        call_command("create_runs", "--confirm")
        self.assertEqual(Run.objects.all().count(), 1)
        self.assertEqual(ConcurrentUsage.objects.all().count(), 0)

    @skip
    @patch("builtins.input", return_value="N")
    def test_handle_no(self, mock_input):
        """Test calling create_runs with no input."""
        call_command("create_runs")
        self.assertEqual(Run.objects.all().count(), 1)
        self.assertEqual(ConcurrentUsage.objects.all().count(), 1)

    @patch("builtins.input", return_value="Y")
    def test_handle_yes(self, mock_input):
        """Test calling create_runs with yes input."""
        call_command("create_runs")
        self.assertEqual(Run.objects.all().count(), 1)
        self.assertEqual(ConcurrentUsage.objects.all().count(), 0)
