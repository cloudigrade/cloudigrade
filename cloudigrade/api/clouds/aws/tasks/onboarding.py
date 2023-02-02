"""Celery tasks related to on-boarding new customer AWS cloud accounts."""
import logging

from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError

from api import error_codes
from api.authentication import get_user_by_account
from api.clouds.aws.util import (
    create_aws_cloud_account,
)
from api.models import User
from util import aws
from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task
from util.exceptions import InvalidArn

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
    logger.info(
        _(
            "Starting configure_customer_aws_and_create_cloud_account for "
            "username='%(username)s' "
            "org_id='%(org_id)s' "
            "customer_arn='%(customer_arn)s' "
            "authentication_id='%(authentication_id)s' "
            "application_id='%(application_id)s' "
            "source_id='%(source_id)s'"
        ),
        {
            "username": username,
            "org_id": org_id,
            "customer_arn": customer_arn,
            "authentication_id": authentication_id,
            "application_id": application_id,
            "source_id": source_id,
        },
    )
    try:
        user = get_user_by_account(account_number=username, org_id=org_id)
    except User.DoesNotExist:
        logger.exception(
            _(
                "Missing user (account_number='%(username)s', org_id='%(org_id)s') "
                "for configure_customer_aws_and_create_cloud_account. "
                "This should never happen and may indicate a database failure!"
            ),
            {"username": username, "org_id": org_id},
        )
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

    logger.info(
        _(
            "Finished configure_customer_aws_and_create_cloud_account for "
            "username='%(username)s' "
            "org_id='%(org_id)s' "
            "customer_arn='%(customer_arn)s' "
            "authentication_id='%(authentication_id)s' "
            "application_id='%(application_id)s' "
            "source_id='%(source_id)s'"
        ),
        {
            "username": username,
            "org_id": org_id,
            "customer_arn": customer_arn,
            "authentication_id": authentication_id,
            "application_id": application_id,
            "source_id": source_id,
        },
    )
