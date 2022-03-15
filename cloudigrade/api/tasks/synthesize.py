"""Tasks for synthesizing data for live service testing."""
import logging
from datetime import timedelta
from functools import partial
from typing import Optional

from celery import shared_task
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.translation import gettext as _
from faker import Faker

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from api.models import SyntheticDataRequest
from api.tests import helper as api_helper  # TODO Don't import from tests module.

logger = logging.getLogger(__name__)
_faker = Faker()
_pyint_negative = partial(_faker.pyint, min_value=-999999, max_value=-1)


def _synthesize_id() -> str:
    """Synthesize an ID that should never collide with real-world IDs."""
    return f"SYNTHETIC-{_faker.uuid4()}"


@shared_task(name="api.tasks.synthesize_user")
@transaction.atomic
def synthesize_user(request_id: int) -> Optional[int]:
    """
    Synthesize a user for the given SyntheticDataRequest ID.

    Args:
        request_id (int): the SyntheticDataRequest.id to process

    Returns:
        int: the same SyntheticDataRequest.id if processing succeeded, else None.
    """
    if not (request := SyntheticDataRequest.objects.filter(id=request_id).first()):
        logger.warning(
            _("SyntheticDataRequest %(id)s does not exist."), {"id": request_id}
        )
        return None
    if request.user:
        logger.warning(
            _("SyntheticDataRequest %(request_id)s already has User %(user_id)s."),
            {"request_id": request_id, "user_id": request.user_id},
        )
        return None

    username = _synthesize_id()
    # Set the user's date_joined far enough in the past so that in a future task we can
    # calculate all past concurrent usage data for synthesized runs that occurred on
    # days earlier than "today".
    user_date_joined = request.created_at - timedelta(days=request.since_days_ago + 1)

    user = User.objects.create_user(
        username=username, is_active=False, date_joined=user_date_joined
    )
    request.user = user
    request.save()

    return request_id


@shared_task(name="api.tasks.synthesize_cloud_accounts")
@transaction.atomic
def synthesize_cloud_accounts(request_id: int) -> Optional[int]:
    """
    Synthesize cloud accounts for the given SyntheticDataRequest ID.

    Args:
        request_id (int): the SyntheticDataRequest.id to process

    Returns:
        int: the same SyntheticDataRequest.id if processing succeeded, else None.
    """
    if not (request := SyntheticDataRequest.objects.filter(id=request_id).first()):
        logger.warning(
            _("SyntheticDataRequest %(id)s does not exist."), {"id": request_id}
        )
        return None
    if not request.user:
        logger.warning(
            _("SyntheticDataRequest %(id)s has no User."), {"id": request_id}
        )
        return None

    for __ in range(request.account_count):
        # Real-world IDs from sources-api are always positive integers. By generating
        # random *negative* integers, they will never collide with actual IDs.
        platform_authentication_id = _pyint_negative()
        platform_application_id = _pyint_negative()
        platform_source_id = _pyint_negative()

        if request.cloud_type == AWS_PROVIDER_STRING:
            aws_account_id = _synthesize_aws_account_id()
            arn = f"arn:aws:iam::{aws_account_id}:role/{_synthesize_id()}"
            api_helper.generate_cloud_account_aws(
                arn=arn,
                user=request.user,
                platform_authentication_id=platform_authentication_id,
                platform_application_id=platform_application_id,
                platform_source_id=platform_source_id,
                platform_application_is_paused=True,
                is_enabled=False,
                is_synthetic=True,
            )
        elif request.cloud_type == AZURE_PROVIDER_STRING:
            api_helper.generate_cloud_account_azure(
                azure_subscription_id=_faker.uuid4(),
                user=request.user,
                platform_authentication_id=platform_authentication_id,
                platform_application_id=platform_application_id,
                platform_source_id=platform_source_id,
                platform_application_is_paused=True,
                is_enabled=False,
                is_synthetic=True,
            )

    logger.info(
        _("Synthesized %(count)s CloudAccounts for SyntheticDataRequest %(id)s"),
        {"count": request.account_count, "id": request.id},
    )
    return request_id


def _synthesize_aws_account_id() -> str:
    """
    Synthesize an AWS account ID that is unlikely to collide with real-world IDs.

    We define the ID in an arbitrarily small domain of 0 to 10**6. AWS account IDs are
    are 12-digit integers, and choosing a random value with several leading 0s *should*
    significantly reduce the likelihood of collisions with current real AWS account IDs,
    though collisions may still be *possible*.
    """
    aws_account_id = f"{_faker.pyint(max_value=10 ** 6):012d}"
    return aws_account_id
