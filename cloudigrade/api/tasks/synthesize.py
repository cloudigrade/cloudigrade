"""Tasks for synthesizing data for live service testing."""
import logging
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.contrib.auth.models import User
from django.db import transaction
from django.utils.translation import gettext as _
from faker import Faker

from api.models import SyntheticDataRequest

logger = logging.getLogger(__name__)
_faker = Faker()


def synthesize_id() -> str:
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

    username = synthesize_id()
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
