"""
Collection of tests specifically to verify fix for Issue 509.

See also: https://gitlab.com/cloudigrade/cloudigrade/issues/509
"""
import faker
from django.test import TestCase

from account import reports
from account.tests import helper as account_helper
from util.tests import helper as util_helper

HOUR = 60. * 60
DAY = HOUR * 24
DAYS_5 = DAY * 5

_faker = faker.Faker()


class ReportBug509TestCase(TestCase):
    """
    Test that Issue 509 is resolved and works as expected.

    Specifically, in this issue, power-off instance events without a defined
    image would not be correctly handled by the "get_account_overviews"
    function, and that resulted in inconsistent output among the other APIs.
    """

    def setUp(self):
        """Set up data for tests."""
        self.user = util_helper.generate_test_user()
        account_created_at = util_helper.utc_dt(2017, 12, 1, 0, 0, 0)
        self.account = account_helper.generate_aws_account(
            user=self.user, created_at=account_created_at,
        )
        self.instance = account_helper.generate_aws_instance(self.account)
        self.image_rhel = account_helper.generate_aws_image(
            rhel_detected=True,
            rhel_challenged=False,
        )

        # Power on the instance before the reporting month.
        self.power_on = util_helper.utc_dt(2017, 12, 25, 12, 34, 56)
        # Power off the instance at the end of the 5th day in the report.
        self.power_off = util_helper.utc_dt(2018, 1, 6, 0, 0, 0)
        account_helper.generate_aws_instance_events(
            self.instance,
            [(self.power_on, self.power_off)],
            self.image_rhel.ec2_ami_id,
        )
        # Report on "month of January in 2018"
        self.start = util_helper.utc_dt(2018, 1, 1, 0, 0, 0)
        self.end = util_helper.utc_dt(2018, 2, 1, 0, 0, 0)

    def test_get_daily_usage(self):
        """Assert appropriate get_daily_usage output."""
        results = reports.get_daily_usage(self.user.id, self.start, self.end)
        for day in results['daily_usage'][:5]:
            self.assertEqual(day['rhel_runtime_seconds'], DAY)
        for day in results['daily_usage'][5:]:
            self.assertEqual(day['rhel_runtime_seconds'], 0)

    def test_get_account_overviews(self):
        """Assert appropriate get_account_overviews output."""
        results = reports.get_account_overviews(self.user.id,
                                                self.start, self.end)
        data = results['cloud_account_overviews'][0]
        self.assertEqual(data['images'], 1)
        self.assertEqual(data['instances'], 1)
        self.assertEqual(data['rhel_instances'], 1)
        self.assertEqual(data['rhel_runtime_seconds'], DAYS_5)

    def test_get_images_overviews(self):
        """Assert appropriate get_images_overviews output."""
        results = reports.get_images_overviews(self.user.id, self.start,
                                               self.end, self.account.id)
        data = results['images'][0]
        self.assertEqual(data['instances_seen'], 1)
        self.assertEqual(data['rhel'], True)
        self.assertEqual(data['rhel_detected'], True)
        self.assertEqual(data['rhel_challenged'], False)
        self.assertEqual(data['runtime_seconds'], DAYS_5)
