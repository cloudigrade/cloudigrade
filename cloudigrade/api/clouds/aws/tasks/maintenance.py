"""Celery tasks related to maintenance functions around AWS."""
import logging

from celery import shared_task

from util.celery import retriable_shared_task

logger = logging.getLogger(__name__)


@retriable_shared_task(name="api.clouds.aws.tasks.repopulate_ec2_instance_mapping")
def repopulate_ec2_instance_mapping():
    """Do nothing.

    This is a placeholder for old in-flight tasks during the shutdown transition.
    """
    # TODO FIXME Delete this function once we're confident no tasks exists.


@shared_task(name="api.clouds.aws.tasks.delete_all_cloudtrails")
def delete_all_cloudtrails():
    """Delete our CloudTrail from all currently known AWS users."""
    from api.clouds.aws.models import AwsCloudAccount

    for account in AwsCloudAccount.objects.all():
        delete_cloudtrail_for_aws_cloud_account_id.delay(account.id)


@retriable_shared_task(
    name="api.clouds.aws.tasks.delete_cloudtrail_for_aws_cloud_account_id"
)
def delete_cloudtrail_for_aws_cloud_account_id(aws_cloud_account_id):
    """Delete our CloudTrail from a specific AWS account."""
    from api.clouds.aws.models import AwsCloudAccount
    from api.clouds.aws.util import delete_cloudtrail

    try:
        return delete_cloudtrail(AwsCloudAccount.objects.get(id=aws_cloud_account_id))
    except AwsCloudAccount.DoesNotExist:
        logger.warning(
            "Cannot delete CloudTrail; no AwsCloudAccount exists with ID %s",
            aws_cloud_account_id,
        )
        return False
