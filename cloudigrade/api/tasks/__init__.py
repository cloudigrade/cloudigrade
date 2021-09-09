"""
Celery tasks for use in the api v2 app.

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

from api.tasks.calculation import (
    calculate_max_concurrent_usage_task,
    fix_problematic_runs,
    recalculate_concurrent_usage_for_all_users,
    recalculate_concurrent_usage_for_user_id,
    recalculate_concurrent_usage_for_user_id_on_date,
    recalculate_runs_for_all_cloud_accounts,
    recalculate_runs_for_cloud_account_id,
)
from api.tasks.inspection import (
    inspect_pending_images,
    persist_inspection_cluster_results_task,
)
from api.tasks.maintenance import (
    delete_cloud_account,
    delete_inactive_users,
    enable_account,
)
from api.tasks.sources import (
    create_from_sources_kafka_message,
    delete_from_sources_kafka_message,
    notify_application_availability_task,
    pause_from_sources_kafka_message,
    unpause_from_sources_kafka_message,
    update_from_source_kafka_message,
)
