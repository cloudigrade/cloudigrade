"""
Celery tasks related to AWS for use in the api v2 app.

Related tasks have been grouped into modules to improve readability of the code.
Only Celery-runnable task functions should be exposed here at the package level.

Note for developers:
If you find yourself adding a new Celery task, please be aware of how Celery
determines which queue to read and write to work on that task. By default,
Celery tasks will go to a queue named "celery". If you wish to separate a task
onto a different queue (which may make it easier to see the volume of specific
waiting tasks), please be sure to update all the relevant configurations to
use that custom queue. This includes CELERY_TASK_ROUTES in config and the
Celery worker's --queues argument (see deployment-configs.yaml in shiftigrade
and related configs in e2e-deploy and saas-templates).
"""

from api.clouds.aws.tasks.cloudtrail import analyze_log
from api.clouds.aws.tasks.imageprep import (
    CLOUD_KEY,
    CLOUD_TYPE_AWS,
    copy_ami_snapshot,
    copy_ami_to_customer_account,
    create_volume,
    delete_snapshot,
    enqueue_ready_volume,
    remove_snapshot_ownership,
)
from api.clouds.aws.tasks.inspection import (
    # persist_aws_inspection_cluster_results,
    run_inspection_cluster,
    scale_down_cluster,
    scale_up_inspection_cluster,
)
from api.clouds.aws.tasks.maintenance import repopulate_ec2_instance_mapping
from api.clouds.aws.tasks.onboarding import (
    configure_customer_aws_and_create_cloud_account,
    initial_aws_describe_instances,
)
from api.clouds.aws.tasks.verification import (
    verify_account_permissions,
    verify_verify_tasks,
)
