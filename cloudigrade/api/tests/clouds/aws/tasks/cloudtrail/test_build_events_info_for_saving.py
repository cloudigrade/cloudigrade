"""Collection of tests for aws.tasks.cloudtrail._build_events_info_for_saving."""
import faker
from django.test import TestCase

from api.clouds.aws.tasks import cloudtrail as tasks
from api.models import InstanceEvent
from api.tests import helper as api_helper
from util.tests import helper as util_helper

_faker = faker.Faker()


class BuildEventsInfoForSavingTest(TestCase):
    """Helper function '_build_events_info_for_saving' test cases."""

    def setUp(self):
        """Set up common variables for tests."""
        self.user = util_helper.generate_test_user()
        self.aws_account_id = util_helper.generate_dummy_aws_account_id()
        self.account = api_helper.generate_cloud_account(
            aws_account_id=self.aws_account_id,
            user=self.user,
            created_at=util_helper.utc_dt(2017, 12, 1, 0, 0, 0),
        )
        api_helper.generate_instance_type_definitions()

    def test_build_events_info_for_saving(self):
        """Test _build_events_info_for_saving with typical inputs."""
        instance = api_helper.generate_instance(self.account)

        # Note: this time is *after* self.account.created_at.
        occurred_at = "2018-01-02T12:34:56+00:00"

        instance_event = api_helper.generate_cloudtrail_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=None,
        )
        events_info = tasks._build_events_info_for_saving(
            self.account, instance, [instance_event]
        )
        self.assertEqual(len(events_info), 1)

    def test_build_events_info_for_saving_too_old_events(self):
        """Test _build_events_info_for_saving with events that are too old."""
        instance = api_helper.generate_instance(self.account)

        # Note: this time is *before* self.account.created_at.
        occurred_at = "2016-01-02T12:34:56+00:00"

        instance_event = api_helper.generate_cloudtrail_instance_event(
            instance=instance,
            occurred_at=occurred_at,
            event_type=InstanceEvent.TYPE.power_on,
            instance_type=None,
        )
        events_info = tasks._build_events_info_for_saving(
            self.account, instance, [instance_event]
        )
        self.assertEqual(len(events_info), 0)
