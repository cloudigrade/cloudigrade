"""Celery tasks related to on-boarding new customer AWS cloud accounts."""
import logging


from botocore.exceptions import ClientError
from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.clouds.aws.models import AwsCloudAccount
from api.clouds.aws.util import (
    create_aws_cloud_account,
    create_initial_aws_instance_events,
    create_missing_power_off_aws_instance_events,
    create_new_machine_images,
    generate_aws_ami_messages,
    start_image_inspection,
)
from util import aws
from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import InvalidArn
from util.misc import lock_task_for_user_ids

logger = logging.getLogger(__name__)


@retriable_shared_task(
    autoretry_for=(RuntimeError,),
    name="api.clouds.aws.tasks.configure_customer_aws_and_create_cloud_account",
)
@rewrap_aws_errors
def configure_customer_aws_and_create_cloud_account(
    username, org_id, customer_arn, authentication_id, application_id, source_id
):
    """
    Configure the customer's AWS account and create our CloudAccount.

    This function is decorated to retry if an unhandled `RuntimeError` is
    raised, which is the exception we raise in `rewrap_aws_errors` if we
    encounter an unexpected error from AWS. This means it should keep retrying
    if AWS is misbehaving.

    Args:
        username (string): Username of the user that will own the new cloud account
        org_id (string): Org Id of the user that will own the new cloud account
        customer_arn (str): customer's ARN
        authentication_id (str): Platform Sources' Authentication object id
        application_id (str): Platform Sources' Application object id
        source_id (str): Platform Sources' Source object id
    """
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        error = error_codes.CG1000
        error.log_internal_message(
            logger, {"application_id": application_id, "username": username}
        )
        error.notify(username, org_id, application_id)
        return
    try:
        getattr(aws.AwsArn(customer_arn), "account_id")
    except InvalidArn:
        error = error_codes.CG1004
        error.log_internal_message(logger, {"application_id": application_id})
        error.notify(username, org_id, application_id)
        return

    try:
        create_aws_cloud_account(
            user,
            customer_arn,
            authentication_id,
            application_id,
            source_id,
        )
    except ValidationError as e:
        logger.info("Unable to create cloud account: error %s", e.detail)


@retriable_shared_task(name="api.clouds.aws.tasks.initial_aws_describe_instances")
@rewrap_aws_errors
def initial_aws_describe_instances(aws_cloud_account_id):
    """
    Fetch and save instances data found upon enabling an AwsCloudAccount.

    Args:
        aws_cloud_account_id (int): the AwsCloudAccount id
    """
    try:
        aws_cloud_account = AwsCloudAccount.objects.get(pk=aws_cloud_account_id)
    except AwsCloudAccount.DoesNotExist:
        logger.warning(
            _("AwsCloudAccount id %s could not be found for initial describe"),
            aws_cloud_account_id,
        )
        # This can happen if a customer creates and then quickly deletes their
        # cloud account before this async task has started to run. Early exit!
        return

    cloud_account = aws_cloud_account.cloud_account.get()
    if not cloud_account.is_enabled:
        logger.warning(
            _("AwsCloudAccount id %s is not enabled; skipping initial describe"),
            aws_cloud_account_id,
        )
        # This can happen if a customer creates and then quickly disabled their
        # cloud account before this async task has started to run. Early exit!
        return

    if cloud_account.platform_application_is_paused:
        logger.warning(
            _("AwsCloudAccount id %s is paused; skipping initial describe"),
            aws_cloud_account_id,
        )
        # This can happen if a customer pauses the sources-api application for an
        # otherwise normally-working cloud account. Early exit!
        return

    arn = aws_cloud_account.account_arn

    session = aws.get_session(arn)
    instances_data = _aws_describe_instances_everywhere(session, aws_cloud_account_id)

    try:
        user_id = cloud_account.user.id
    except User.DoesNotExist:
        logger.info(
            _(
                "User for account id %s has already been deleted; "
                "skipping initial describe."
            ),
            aws_cloud_account_id,
        )
        # This can happen if a customer creates and then quickly deletes their
        # cloud account before this async task has started to run. If the user has
        # no other cloud accounts the user will also be deleted. Early exit!
        return

    # Lock the task at a user level. A user can only run one task at a time.
    with lock_task_for_user_ids([user_id]):
        try:
            # Explicitly "get" the related AwsCloudAccount before proceeding.
            # We do this at the start of this transaction in case the account has been
            # deleted during the potentially slow describe_instances_everywhere above.
            # If this fails, we'll jump to the except block to log an important warning.
            AwsCloudAccount.objects.get(pk=aws_cloud_account_id)

            create_missing_power_off_aws_instance_events(cloud_account, instances_data)
            new_ami_ids = create_new_machine_images(session, instances_data)
            logger.info(
                _("Created new machine images include: %(new_ami_ids)s"),
                {"new_ami_ids": new_ami_ids},
            )
            create_initial_aws_instance_events(cloud_account, instances_data)
        except AwsCloudAccount.DoesNotExist:
            logger.warning(
                _(
                    "AwsCloudAccount id %s could not be found to save newly "
                    "discovered images and instances"
                ),
                aws_cloud_account_id,
            )
            # This can happen if a customer deleted their cloud account between
            # the start of this function and here. The AWS calls for
            # describe_instances_everywhere may be slow and are not within this
            # transaction. That's why we have to check again after it.
            return

    messages = generate_aws_ami_messages(instances_data, new_ami_ids)
    for message in messages:
        start_image_inspection(str(arn), message["image_id"], message["region"])


def _aws_describe_instances_everywhere(session, aws_cloud_account_id):
    """
    Describe all instances for the Aws session specified.

    Args:
        session (boto3.Session): A temporary session tied to a customer account
        aws_cloud_account_id (int): the AwsCloudAccount id

    Returns:
        dict: Lists of instance IDs keyed by region where they were found.
    """
    try:
        instances_data = aws.describe_instances_everywhere(session)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "RequestLimitExceeded":
            logger.info(
                _(
                    "RequestLimitExceeded while trying to DescribeInstances"
                    " for AwsCloudAccount id %s"
                ),
                aws_cloud_account_id,
            )
        raise e

    return instances_data
