"""Collection of tests for the 'seed_review_data' management command."""

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

from api.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    Run,
)


class SyncBucketLifecycleTest(TestCase):
    """Management command 'seed_review_data' test case."""

    def test_command_output(self):
        """Test that 'seed_review_data' correctly calls seeds data."""
        call_command("seed_review_data")

        self.assertEquals(User.objects.count(), 2)
        self.assertEquals(AwsCloudAccount.objects.count(), 5)
        self.assertEquals(AwsMachineImage.objects.count(), 8)
        self.assertEquals(AwsInstance.objects.count(), 11)
        self.assertEquals(AwsInstanceEvent.objects.count(), 28)
        self.assertEquals(Run.objects.count(), 16)
