"""Celery app for use in Django project."""
import json
import logging
import uuid

import django
import environ
import sentry_sdk
from celery import Celery, current_task, signals
from django.conf import settings
from sentry_sdk.integrations.celery import CeleryIntegration

from util.middleware import local

env = environ.Env()
logger = logging.getLogger(__name__)


logger.info("Starting celery.")
# Django setup is required *before* Celery app can start correctly.
django.setup()
logger.info("Django setup.")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Remember: the "schedule" values are integer numbers of seconds.
app.conf.beat_schedule = {
    # Enabled Tasks
    "delete_inactive_users": {
        "task": "api.tasks.delete_inactive_users",
        "schedule": env.int("DELETE_INACTIVE_USERS_SCHEDULE", default=24 * 60 * 60),
    },
    "delete_orphaned_cloud_accounts": {
        "task": "api.tasks.delete_orphaned_cloud_accounts",
        "schedule": env.int("DELETE_ORPHANED_ACCOUNTS_SCHEDULE", default=24 * 60 * 60),
    },
    "persist_inspection_cluster_results": {
        "task": "api.tasks.persist_inspection_cluster_results_task",
        "schedule": env.int(
            "HOUNDIGRADE_ECS_PERSIST_INSPECTION_RESULTS_SCHEDULE", default=60
        ),
    },
    "inspect_pending_images": {
        "task": "api.tasks.inspect_pending_images",
        "schedule": env.int("INSPECT_PENDING_IMAGES_SCHEDULE", default=15 * 60),
    },
    "recalculate_runs_for_all_cloud_accounts": {
        "task": "api.tasks.recalculate_runs_for_all_cloud_accounts",
        "schedule": env.int(
            "RECALCULATE_RUNS_FOR_ALL_CLOUD_ACCOUNTS_SCHEDULE",
            default=60 * 60,  # hourly
        ),
    },
    "recalculate_concurrent_usage_for_all_users": {
        "task": "api.tasks.recalculate_concurrent_usage_for_all_users",
        "schedule": env.int(
            "RECALCULATE_CONCURRENT_USAGE_FOR_ALL_USERS_SCHEDULE",
            default=60 * 60,  # hourly
        ),
    },
    "analyze_log_every_2_mins": {
        "task": "api.clouds.aws.tasks.analyze_log",
        "schedule": env.int("ANALYZE_LOG_SCHEDULE", default=30),
    },
    "repopulate_ec2_instance_mapping_every_week": {
        "task": "api.clouds.aws.tasks.repopulate_ec2_instance_mapping",
        "schedule": env.int(
            "AWS_REPOPULATE_EC2_INSTANCE_MAPPING_SCHEDULE",
            default=60 * 60 * 24 * 7,  # 1 week in seconds
        ),
    },
    "repopulate_azure_instance_mapping_every_week": {
        "task": "api.clouds.azure.tasks.repopulate_azure_instance_mapping",
        "schedule": env.int(
            "REPOPULATE_AZURE_INSTANCE_MAPPING_SCHEDULE",
            default=60 * 60 * 24 * 7,  # 1 week in seconds
        ),
    },
    "ensure_all_verify_tasks_are_valid": {
        "task": "api.clouds.aws.tasks.ensure_all_verify_tasks_are_valid",
        "schedule": env.int("VERIFY_VERIFY_TASKS_SCHEDULE", default=60 * 60),
    },
    # Disabled Tasks
    "scale_up_inspection_cluster_every_60_min": {
        "task": "api.clouds.aws.tasks.scale_up_inspection_cluster",
        "schedule": 999999,
        "enabled": False,
    },
}
task_packages = ["api.clouds.aws.tasks", "api.clouds.azure.tasks", "api.tasks"]
app.autodiscover_tasks(task_packages)
logger.info("Celery setup.")

if env("CELERY_ENABLE_SENTRY", default=False):
    logger.info("Enabling sentry.")

    CELERY_SENTRY_SAMPLE_RATE_DEFAULT = env.float(
        "CELERY_SENTRY_SAMPLE_RATE_DEFAULT", default=0.1
    )
    # CELERY_SENTRY_SAMPLE_RATE_BY_TASK_NAME example value:
    # '{"api.tasks.enable_account": "0.5", "api.clouds.aws.tasks.analyze_log": "0.1"}'
    CELERY_SENTRY_SAMPLE_RATE_BY_TASK_NAME = json.loads(
        env.str("CELERY_SENTRY_SAMPLE_RATE_BY_TASK_NAME", default="{}")
    )

    def celery_traces_sampler(sampling_context):
        """Determine Sentry trace sampler rate for the given context."""
        context_task_name = sampling_context.get("celery_job", {}).get("task")
        if context_task_name in CELERY_SENTRY_SAMPLE_RATE_BY_TASK_NAME:
            return CELERY_SENTRY_SAMPLE_RATE_BY_TASK_NAME[context_task_name]
        return CELERY_SENTRY_SAMPLE_RATE_DEFAULT

    CELERY_SENTRY_RELEASE = (
        settings.CLOUDIGRADE_VERSION
        if settings.CLOUDIGRADE_VERSION
        else env("CELERY_SENTRY_RELEASE")
    )
    sentry_sdk.init(
        dsn=env("CELERY_SENTRY_DSN"),
        environment=env("CELERY_SENTRY_ENVIRONMENT"),
        release=CELERY_SENTRY_RELEASE,
        traces_sampler=celery_traces_sampler,
        integrations=[CeleryIntegration()],
    )
    logger.info("Sentry setup.")


@signals.before_task_publish.connect
def insert_request_id(headers=None, **kwargs):
    """
    Insert request_id into task headers.

    This is so we can log the same request_id in our task.
    If the task is not launched from a user request, generate
    a new request_id and use that.
    """
    request_id = getattr(local, "request_id", None)
    if request_id is None:
        request_id = uuid.uuid4()
    headers["request_id"] = request_id


@signals.task_prerun.connect
def setup_request_id(**kwargs):
    """Set request_id from current task header."""
    request_id = current_task.request.get("request_id", None)
    local.request_id = request_id


@signals.task_postrun.connect
def cleanup_request_id(**kwargs):
    """Clean up request_id from the thread."""
    local.request_id = None


if env.bool("CELERY_DISABLE_LOGGING_HIJACK", default=True):

    @signals.setup_logging.connect
    def on_celery_setup_logging(**kwargs):
        """
        Stop celery from overriding default logging setup.

        By default celery hijacks the root logger. The configuration setting
        CELERYD_HIJACK_ROOT_LOGGER only stops celery from updating the handler,
        celery still updates the formatter and we lose the filter.

        Since the formatter we want to use is the configured Django one,
        we can just configure celery to not touch logging.
        """
        pass
