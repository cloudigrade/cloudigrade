#!/usr/bin/env python
"""Simple CLI program to create a notification from a bucket to a queue."""

import argparse

import boto3


def add_notification(bucket_name, sqs_arn):
    """Create notification to from bucket to queue.

    For any object created in the bucket, a notification will be sent to the
    queue.
    """
    client = boto3.client('s3')
    bucket_notifications_config = {
        'QueueConfigurations': [{
            'Id': 'Notifications',
            'QueueArn': sqs_arn,
            'Events': ['s3:ObjectCreated:*'],
            'Filter': {
                'Key': {
                    'FilterRules': [
                        {
                            'Name': 'prefix',
                            'Value': 'AWSLogs/'
                            },
                        {
                            'Name': 'suffix',
                            'Value': '.json.gz'
                            },
                        ]
                    }
                },
        }]
    }
    client.put_bucket_notification_configuration(
        Bucket=bucket_name,
        NotificationConfiguration=bucket_notifications_config
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='The s3 bucket name.')
    parser.add_argument(
        '--bucket ',
        required=True,
        default=None,
        action='store',
        dest='bucket_name',
        type=str,
        help=('Name of the s3 bucket to add notification to.')
    )
    parser.add_argument(
        '--queue ',
        required=True,
        default=None,
        action='store',
        dest='sqs_arn',
        type=str,
        help=('Arn of the queue to.')
    )
    args = parser.parse_args()

    add_notification(args.bucket_name, args.sqs_arn)
