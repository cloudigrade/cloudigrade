"""Helper utility package to wrap up common AWS operations."""
from util.aws.arn import AwsArn
from util.aws.autoscaling import (
    describe_auto_scaling_group,
    is_scaled_down,
    scale_down,
    scale_up,
)
from util.aws.cloudtrail import (
    configure_cloudtrail,
    disable_cloudtrail,
    get_cloudtrail_name,
)
from util.aws.ec2 import (
    InstanceState,
    add_snapshot_ownership,
    check_snapshot_state,
    check_volume_state,
    copy_ami,
    copy_snapshot,
    create_volume,
    describe_image,
    describe_images,
    describe_instances,
    describe_instances_everywhere,
    get_ami,
    get_ami_snapshot_id,
    get_snapshot,
    get_volume,
    is_windows,
    remove_snapshot_ownership,
)
from util.aws.helper import (
    get_region_from_availability_zone,
    get_regions,
    rewrap_aws_errors,
    verify_account_access,
)
from util.aws.s3 import get_object_content_from_s3
from util.aws.sqs import (
    SQS_RECEIVE_BATCH_SIZE,
    SQS_SEND_BATCH_SIZE,
    add_messages_to_queue,
    create_queue,
    delete_messages_from_queue,
    ensure_queue_has_dlq,
    extract_sqs_message,
    get_sqs_queue_url,
    read_messages_from_queue,
    receive_messages_from_queue,
    yield_messages_from_queue,
)
from util.aws.sts import get_session, get_session_account_id

OPENSHIFT_TAG = "cloudigrade-ocp-present"
RHEL_TAG = "cloudigrade-rhel-present"
