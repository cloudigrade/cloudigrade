"""Helper utility package to wrap up common AWS operations."""
from util.aws.arn import AwsArn
from util.aws.autoscaling import (
    describe_auto_scaling_group,
    is_scaled_down,
    scale_down,
    scale_up,
)
from util.aws.cloudtrail import (
    delete_cloudtrail,
    get_cloudtrail_name,
)
from util.aws.helper import (
    COMMON_AWS_ACCESS_DENIED_ERROR_CODES,
    get_regions,
    rewrap_aws_errors,
    verify_account_access,
)
from util.aws.sts import get_session, get_session_account_id


ECS_CLUSTER_REGION = "us-east-1"  # For now, our cluster is *always* in us-east-1.

AWS_PRODUCT_CODE_TYPE_MARKETPLACE = "marketplace"
