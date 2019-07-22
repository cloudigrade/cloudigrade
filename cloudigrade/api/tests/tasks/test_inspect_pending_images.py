"""Collection of tests for tasks.inspect_pending_images."""
import datetime
from unittest.mock import call, patch

from django.test import TestCase

from api import tasks
from api.models import MachineImage
from api.tests import helper as account_helper
from util.misc import get_now


class InspectPendingImagesTest(TestCase):
    """Celery task 'inspect_pending_images' test cases."""

    def test_inspect_pending_images(self):
        """
        Test that only old "pending" images are found and reinspected.

        Note that we effectively time-travel here to points in the past to
        create the account, images, and instances. This is necessary because
        updated_at is automatically set by Django and cannot be manually set,
        but we need things with specific older updated_at times.
        """
        real_now = get_now()
        yesterday = real_now - datetime.timedelta(days=1)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = yesterday
            account = account_helper.generate_aws_account()
            image_old_inspected = account_helper.generate_aws_image()
            image_old_pending = account_helper.generate_aws_image(
                status=MachineImage.PENDING
            )
            # an instance exists using old inspected image.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_old_inspected
            )
            # an instance exists using old pending image.
            instance_old_pending = account_helper.generate_aws_instance(
                cloud_account=account, image=image_old_pending
            )
            # another instance exists using the same old pending image, but the
            # image should still only be reinspected once regardless of how
            # many instances used it.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_old_pending
            )

        one_hour_ago = real_now - datetime.timedelta(seconds=60 * 60)
        with patch('django.utils.timezone.now') as mock_now:
            mock_now.return_value = one_hour_ago
            image_new_inspected = account_helper.generate_aws_image()
            image_new_pending = account_helper.generate_aws_image(
                status=MachineImage.PENDING
            )
            # an instance exists using new inspected image.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_new_inspected
            )
            # an instance exists using new pending image, but it should not
            # trigger inspection because the image is not old enough.
            account_helper.generate_aws_instance(
                cloud_account=account, image=image_new_pending
            )

        expected_calls = [
            call(
                account.content_object.account_arn,
                image_old_pending.content_object.ec2_ami_id,
                instance_old_pending.content_object.region,
            )
        ]
        with patch.object(tasks, 'start_image_inspection') as mock_start:
            tasks.inspect_pending_images()
            mock_start.assert_has_calls(expected_calls, any_order=True)
