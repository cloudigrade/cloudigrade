"""
Celery tasks related to AWS for use in the api v2 app.

Related tasks have been grouped into modules to improve readability of the code.
Only Celery-runnable task functions should be exposed here at the package level.

Important notes for developers:

If you find yourself adding a new Celery task, please be aware of how Celery
determines which queue to read and write to work on that task. By default,
Celery tasks will go to a queue named "celery". If you wish to separate a task
onto a different queue (which may make it easier to see the volume of specific
waiting tasks), please be sure to update all the relevant configurations to
use that custom queue. This includes CELERY_TASK_ROUTES in config and the
Celery worker's --queues argument (see related openshift deployment config files
elsewhere and in related repos like e2e-deploy and saas-templates).

Please also include a specific name in each task decorator. If a task function
is ever moved in the future, but it was previously using automatic names, that
will cause a problem if Celery tries to execute an instance of a task that was
created *before* the function moved. Why? The old automatic name will not match
the new automatic name, and Celery cannot know that the two were once the same.
Therefore, we should always preserve the original name in each task function's
decorator even if the function itself is renamed or moved elsewhere.
"""

import logging

from celery import shared_task

# IMPORTANT NOTE: DO NOT LET PYCHARM, ISORT, etc REARRANGE api.clouds.aws.tasks IMPORTS.
# There are still, as of the time of this comment, interdependencies among these tasks,
# and rearranging these imports *may* result in problematic circular imports.
from api.clouds.aws.tasks.cloudtrail import analyze_log
from api.clouds.aws.tasks.inspection import launch_inspection_instance
from api.clouds.aws.tasks.imageprep import (
    CLOUD_KEY,
    CLOUD_TYPE_AWS,
    copy_ami_snapshot,
    copy_ami_to_customer_account,
    delete_snapshot,
    remove_snapshot_ownership,
)
from api.clouds.aws.tasks.maintenance import repopulate_ec2_instance_mapping
from api.clouds.aws.tasks.onboarding import (
    configure_customer_aws_and_create_cloud_account,
    initial_aws_describe_instances,
)

#
# Begin the horrible temporary kludges for deprecated celery tasks...
#

logger = logging.getLogger(__name__)


@shared_task(name="api.clouds.aws.tasks.create_volume")
def create_volume(*args, **kwargs):
    """Do nothing when running deprecated create_volume task."""
    logger.error("create_volume is deprecated")


@shared_task(name="api.clouds.aws.tasks.enqueue_ready_volume")
def enqueue_ready_volume(*args, **kwargs):
    """Do nothing when running deprecated enqueue_ready_volume task."""
    logger.error("enqueue_ready_volume is deprecated")


@shared_task(name="api.clouds.aws.tasks.attach_volumes_to_cluster")
def attach_volumes_to_cluster(*args, **kwargs):
    """Do nothing when running deprecated attach_volumes_to_cluster task."""
    logger.error("attach_volumes_to_cluster is deprecated")


@shared_task(name="api.clouds.aws.tasks.run_inspection_cluster")
def run_inspection_cluster(*args, **kwargs):
    """Do nothing when running deprecated run_inspection_cluster task."""
    logger.error("run_inspection_cluster is deprecated")


@shared_task(name="api.clouds.aws.tasks.scale_down_cluster")
def scale_down_cluster(*args, **kwargs):
    """Do nothing when running deprecated scale_down_cluster task."""
    logger.error("scale_down_cluster is deprecated")


@shared_task(name="api.clouds.aws.tasks.scale_up_inspection_cluster")
def scale_up_inspection_cluster(*args, **kwargs):
    """Do nothing when running deprecated scale_up_inspection_cluster task."""
    logger.error("scale_up_inspection_cluster is deprecated")


@shared_task(name="api.clouds.aws.tasks.verify_verify_tasks")
def verify_verify_tasks(*args, **kwargs):
    """Do nothing when running deprecated verify_verify_tasks task."""
    logger.error("verify_verify_tasks is deprecated")
