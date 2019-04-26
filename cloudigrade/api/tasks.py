"""
Celery tasks for use in the api v2 app.

Note for developers:
If you find yourself adding a new Celery task, please be aware of how Celery
determines which queue to read and write to work on that task. By default,
Celery tasks will go to a queue named "celery". If you wish to separate a task
onto a different queue (which may make it easier to see the volume of specific
waiting tasks), please be sure to update all the relevant configurations to
use that custom queue. This includes CELERY_TASK_ROUTES in config and the
Celery worker's --queues argument (see deployment-configs.yaml in shiftigrade).
"""
import logging

from util.aws import rewrap_aws_errors
from util.celery import retriable_shared_task


logger = logging.getLogger(__name__)

# Constants
CLOUD_KEY = 'cloud'
CLOUD_TYPE_AWS = 'aws'
HOUNDIGRADE_MESSAGE_READ_LEN = 10


@retriable_shared_task
@rewrap_aws_errors
def initial_aws_describe_instances(account_id):
    """
    TODO Fetch and save instances data found upon AWS cloud account creation.

    Args:
        account_id (int): the AwsAccount id
    """
    pass
