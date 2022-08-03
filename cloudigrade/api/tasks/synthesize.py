"""
Tasks for synthesizing data for live service testing.

Many of these tasks return the exact same arguments they are given, assuming they
complete successfully, in order to facilitate task chaining or chording.
"""
import logging
import secrets
import uuid
from datetime import date, datetime, timedelta
from math import ceil
from typing import Optional

from celery import chord, group, shared_task
from dateutil import rrule
from django.db import transaction
from django.utils.translation import gettext as _

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from api.models import CloudAccount, Instance, SyntheticDataRequest
from api.models import User
from api.tests import helper as api_helper  # TODO Don't import from tests module.
from util.misc import get_now

logger = logging.getLogger(__name__)
random = secrets.SystemRandom()


def _synthesize_id() -> str:
    """Synthesize an ID that should never collide with real-world IDs."""
    return f"SYNTHETIC-{uuid.uuid4()}"


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

    account_number = _synthesize_id()
    org_id = _synthesize_id()
    # Set the user's date_joined far enough in the past so that in a future task we can
    # calculate all past concurrent usage data for synthesized runs that occurred on
    # days earlier than "today".
    user_date_joined = request.created_at - timedelta(days=request.since_days_ago + 1)

    user = User.objects.create_user(
        account_number=account_number,
        org_id=org_id,
        is_active=False,
        date_joined=user_date_joined,
        is_permanent=False,
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
        platform_authentication_id = random.randrange(-999999, -1)
        platform_application_id = random.randrange(-999999, -1)
        platform_source_id = random.randrange(-999999, -1)

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
                azure_subscription_id=uuid.uuid4(),
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
    aws_account_id = f"{random.randrange(0, 10 ** 6):012d}"
    return aws_account_id


@shared_task(name="api.tasks.synthesize_images")
@transaction.atomic
def synthesize_images(request_id: int) -> Optional[int]:
    """
    Synthesize images for the given SyntheticDataRequest ID.

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
    if not (cloud_accounts := list(CloudAccount.objects.filter(user=request.user))):
        logger.warning(
            _("SyntheticDataRequest %(id)s has no CloudAccount."), {"id": request_id}
        )
        return None

    for __ in range(request.image_count):
        rhel_detected = random.random() < request.image_rhel_chance
        openshift_detected = random.random() < request.image_ocp_chance

        if request.cloud_type == AWS_PROVIDER_STRING:
            owner_aws_account_id = (
                _synthesize_aws_account_id()
                if random.random() <= request.image_other_owner_chance
                else random.choice(cloud_accounts).content_object.aws_account_id
            )
            image = api_helper.generate_image_aws(
                rhel_detected=rhel_detected,
                openshift_detected=openshift_detected,
                owner_aws_account_id=owner_aws_account_id,
                ec2_ami_id=_synthesize_id(),
                name=_synthesize_id(),
            )
            request.machine_images.add(image)
        elif request.cloud_type == AZURE_PROVIDER_STRING:
            image = api_helper.generate_image_azure(
                rhel_detected=rhel_detected, openshift_detected=openshift_detected
            )
            request.machine_images.add(image)

    logger.info(
        _("Synthesized %(count)s MachineImages for SyntheticDataRequest %(id)s"),
        {"count": request.image_count, "id": request.id},
    )
    return request_id


@shared_task(name="api.tasks.synthesize_instances")
@transaction.atomic
def synthesize_instances(request_id: int) -> Optional[int]:
    """
    Synthesize instances for the given SyntheticDataRequest ID.

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
    if not (cloud_accounts := list(CloudAccount.objects.filter(user=request.user))):
        logger.warning(
            _("SyntheticDataRequest %(id)s has no CloudAccount."), {"id": request_id}
        )
        return None
    if not (images := request.machine_images.all()):
        logger.warning(
            _("SyntheticDataRequest %(id)s has no MachineImage."), {"id": request_id}
        )
        return None

    for __ in range(request.instance_count):
        cloud_account = random.choice(cloud_accounts)
        image = random.choice(images)

        if request.cloud_type == AWS_PROVIDER_STRING:
            api_helper.generate_instance_aws(
                cloud_account=cloud_account,
                image=image,
                ec2_instance_id=_synthesize_id(),
            )
        elif request.cloud_type == AZURE_PROVIDER_STRING:
            api_helper.generate_instance_azure(
                cloud_account=cloud_account,
                image=image,
                azure_instance_resource_id=_synthesize_id(),
            )

    logger.info(
        _("Synthesized %(count)s Instances for SyntheticDataRequest %(id)s"),
        {"count": request.instance_count, "id": request_id},
    )
    return request_id


@shared_task(name="api.tasks.synthesize_instance_events")
@transaction.atomic
def synthesize_instance_events(request_id: int) -> Optional[int]:
    """
    Synthesize events for all Instances for the given SyntheticDataRequest ID.

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
    if not (
        instances := Instance.objects.filter(cloud_account__user_id=request.user_id)
    ):
        logger.warning(
            _("SyntheticDataRequest %(id)s has no Instance."), {"id": request_id}
        )
        return None

    run_times = _synthesize_run_times(
        request.since_days_ago,
        request.hours_per_run_min,
        request.hours_per_run_mean,
        request.run_count_per_instance_min,
        request.run_count_per_instance_mean,
        request.hours_between_runs_mean,
        request.instance_count,
    )

    for instance, run_times in zip(instances, run_times):
        api_helper.generate_instance_events(instance, run_times)

    return request_id


def _synthesize_run_times(
    since_days_ago: int,
    hours_per_run_min: float,
    hours_per_run_mean: float,
    run_count_per_instance_min: int,
    run_count_per_instance_mean: int,
    hours_between_runs_mean: float,
    instance_count: int,
) -> list[list[tuple[datetime, datetime]]]:
    """
    Synthesize pairs of pseudorandom datetime objects representing run starts and ends.

    This function returns a list of list of tuples. The outer list length matches the
    number of instances. Each outer list element has a list of (start, end) tuples.
    """
    now = get_now()
    since_seconds_ago = since_days_ago * 24 * 60 * 60

    secs_per_run_min = int(hours_per_run_min * 3600)
    secs_per_run_mean = max(secs_per_run_min, int(hours_per_run_mean * 3600))
    secs_per_run_max = secs_per_run_mean * 2 - secs_per_run_min
    run_count_min = run_count_per_instance_min
    run_count_mean = run_count_per_instance_mean
    run_count_max = int(run_count_mean * 2)
    max_secs_between_runs = int(hours_between_runs_mean * 3600 * 2)

    instances_run_times = []  # For each instance, a list of tuples defining run times.

    for __ in range(instance_count):
        # How many runs to define for this instance.
        run_count_to_make = max(
            run_count_min,
            min(
                ceil(random.normalvariate(run_count_mean, run_count_max / 5) - 0.5),
                run_count_max,
            ),
        )
        # How long should each run last.
        run_durations = [
            int(random.uniform(secs_per_run_min, secs_per_run_max))
            for ___ in range(run_count_to_make)
        ]
        # How much time before the next run starts.
        # First element is 0 because we will calculate an initial starting delay later.
        delays_between_runs = [0] + [
            int(random.uniform(1, max_secs_between_runs))
            for ___ in range(run_count_to_make - 1)
        ]
        total_duration = sum(run_durations) + sum(delays_between_runs)
        average_duration = (
            total_duration / run_count_to_make if run_count_to_make else 0
        )

        # How soon after the "since" time should the first run start?
        # Subtract the total duration to try fitting most of the runs within the time,
        # but the average duration of one of the runs to increase a chance that
        # the final run will actually not have ended yet. Then pick a random value
        # from zero to that number to be the first offset from the "since" time.
        # Don't let that value be negative, though, which could happen if the cumulative
        # requested run time is too large
        initial_delay = max(
            int(random.uniform(0, average_duration)),
            int(
                random.uniform(0, since_seconds_ago - total_duration + average_duration)
            ),
        )
        delays_between_runs[0] = initial_delay

        # Initialize baseline start and stop times at since_seconds_ago from now.
        # The run times will be created using increasing offsets from these two.
        start_time = now - timedelta(seconds=since_seconds_ago)
        stop_time = start_time

        run_times = []  # List of (start, end) tuples for this instance's run times.
        for delay, duration in zip(delays_between_runs, run_durations):
            start_time = stop_time + timedelta(seconds=delay)
            stop_time = start_time + timedelta(seconds=duration)

            # If this would start in the future, we've gone too far!
            if start_time > now:
                break

            # If this would stop in the future, keep the run with no stop time, meaning
            # it is "still running", and we must stop creating more runs.
            if stop_time > now:
                run_times.append((start_time, None))
                break
            run_times.append((start_time, stop_time))
        instances_run_times.append(run_times)

    return instances_run_times


@shared_task(name="api.tasks.synthesize_runs_and_usage")
def synthesize_runs_and_usage(request_id: int) -> Optional[int]:
    """
    Trigger calculation of Run and ConcurrentUsage data for recently-synthesized data.

    Note that this task calls (and chords) additional tasks asynchronously. This means
    callers should not expect all of the "inner" calculations to have completed by the
    time *this* function has returned. This differs from other synthesize_ tasks that
    can be chained together with the expectation that one has completed before the next.

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
    if not (instances := Instance.objects.filter(cloud_account__user=request.user)):
        logger.warning(
            _("SyntheticDataRequest %(id)s has no Instance."), {"id": request_id}
        )
        return None

    # Locally import other tasks to avoid potential import loops.
    from api.tasks import recalculate_runs_for_instance_id

    recalculate_runs_tasks = [
        recalculate_runs_for_instance_id.s(instance.id) for instance in instances
    ]

    active_dates = [
        _datetime.date()
        for _datetime in rrule.rrule(
            freq=rrule.DAILY,
            dtstart=request.user.date_joined.date(),
            until=request.created_at.date(),
        )
    ]
    recalculate_concurrent_tasks = [
        synthesize_concurrent_usage.s(request.user.id, _date) for _date in active_dates
    ]

    # Important note! apply_async with serializer="pickle" is required *here* because
    # nested task calls constructed through `chord` or `group` appear to ignore the
    # serializer definitions on those nested task functions, specifically here in
    # synthesize_concurrent_usage. This feels wrong and may be a Celery bug, but without
    # forcing the serializer from the outermost call here, serialization fails
    # catastrophically in the nested task.
    chord(
        group(recalculate_runs_tasks),
        group(recalculate_concurrent_tasks),
    ).apply_async(serializer="pickle")

    return request_id


@shared_task(name="api.tasks.synthesize_concurrent_usage", serializer="pickle")
def synthesize_concurrent_usage(__: object, user_id: int, on_date: date) -> int:
    """
    Wrap recalculate_concurrent_usage_for_user_id for use at the end of a Celery chain.

    Celery callbacks and chains require subsequent tasks to accept the preceding tasks'
    results as additional arguments *before* the final task's own arguments. Since we
    don't care about task results here and there appears to be no way to disable this
    behavior, this wrapper task effectively discards that first argument.
    """
    from api.tasks import recalculate_concurrent_usage_for_user_id_on_date

    recalculate_concurrent_usage_for_user_id_on_date(user_id, on_date)
    return user_id
