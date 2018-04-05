from celery import shared_task

from django.conf import settings

from util import aws


@shared_task
def copy_ami_snapshot(arn, ami_id, source_region):
    session = aws.get_session(arn)
    # 1. Get snapshot ID for AMI
    ami = aws.get_ami(session, ami_id)
    snapshot_id = aws.get_ami_snapshot_id(ami)
    # 2. Modify snapshot permissions so we can copy it
    aws.change_snapshot_ownership(session, snapshot_id, operation='Add')
    # 3. Copy snapshot to our region + AZ
    aws.copy_snapshot(snapshot_id, source_region)
