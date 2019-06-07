"""Helper utility module to wrap up common AWS STS operations."""
import json

import boto3

from util.aws.arn import AwsArn

cloudigrade_policy = {
    'Version': '2012-10-17',
    'Statement': [
        {
            'Sid': 'CloudigradePolicy',
            'Effect': 'Allow',
            'Action': [
                'ec2:DescribeImages',
                'ec2:DescribeInstances',
                'ec2:ModifySnapshotAttribute',
                'ec2:DescribeSnapshotAttribute',
                'ec2:DescribeSnapshots',
                'ec2:CopyImage',
                'ec2:CreateTags',
                'ec2:DescribeRegions',
                'cloudtrail:CreateTrail',
                'cloudtrail:UpdateTrail',
                'cloudtrail:PutEventSelectors',
                'cloudtrail:DescribeTrails',
                'cloudtrail:StartLogging',
                'cloudtrail:StopLogging',
            ],
            'Resource': '*'
        }
    ]
}


def get_session(arn, region_name='us-east-1'):
    """
    Return a session using the customer AWS account role ARN.

    Args:
        arn (str): Amazon Resource Name to use for assuming a role.
        region_name (str): Default AWS Region to associate newly
        created clients with.

    Returns:
        boto3.Session: A temporary session tied to a customer account

    """
    sts = boto3.client('sts')
    awsarn = AwsArn(arn)
    response = sts.assume_role(
        Policy=json.dumps(cloudigrade_policy),
        RoleArn='{0}'.format(awsarn),
        RoleSessionName='cloudigrade-{0}'.format(awsarn.account_id)
    )
    response = response['Credentials']
    return boto3.Session(
        aws_access_key_id=response['AccessKeyId'],
        aws_secret_access_key=response['SecretAccessKey'],
        aws_session_token=response['SessionToken'],
        region_name=region_name
    )


def get_session_account_id(session):
    """Return the account ID for the given AWS session."""
    return session.client('sts').get_caller_identity().get('Account')


def _get_primary_account_id():
    """Return the account ID for the primary AWS account."""
    return boto3.client('sts').get_caller_identity().get('Account')
