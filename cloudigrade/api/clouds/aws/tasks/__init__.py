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

# IMPORTANT NOTE: DO NOT LET PYCHARM, ISORT, etc REARRANGE api.clouds.aws.tasks IMPORTS.
# There are still, as of the time of this comment, interdependencies among these tasks,
# and rearranging these imports *may* result in problematic circular imports.
from api.clouds.aws.tasks.cloudtrail import analyze_log
from api.clouds.aws.tasks.inspection import launch_inspection_instance
from api.clouds.aws.tasks.imageprep import (
    copy_ami_snapshot,
    copy_ami_to_customer_account,
    delete_snapshot,
    remove_snapshot_ownership,
)
from api.clouds.aws.tasks.maintenance import (
    delete_all_cloudtrails,
    delete_cloudtrail_for_aws_cloud_account_id,
)
from api.clouds.aws.tasks.onboarding import (
    configure_customer_aws_and_create_cloud_account,
    initial_aws_describe_instances,
)
