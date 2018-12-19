"""Ensure S3 bucket lifecycle settings are up to date."""
import boto3
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _


class Command(BaseCommand):
    """Ensure S3 bucket lifecycle settings are up to date."""

    help = _('Ensures S3 bucket lifecycle settings are up to date.')

    bucket_name = settings.S3_BUCKET_NAME

    def handle(self, *args, **options):
        """Handle the command execution."""
        s3 = boto3.resource('s3')
        bucket_lifecycle_configuration = \
            s3.BucketLifecycleConfiguration(self.bucket_name)
        bucket_lifecycle_configuration.put(
            LifecycleConfiguration={
                'Rules': [
                    {
                        'Expiration': {
                            'Days': settings.S3_BUCKET_LC_MAX_AGE
                        },
                        'ID': settings.S3_BUCKET_LC_NAME,
                        'Status': 'Enabled',
                        # This looks weird, empty prefix and filter and all
                        # but without it, AWS throws an equivalent of a 400
                        'Filter': {
                            'Prefix': ''
                        },
                        'Transitions': [
                            {
                                'Days': settings.S3_BUCKET_LC_IA_TRANSITION,
                                'StorageClass': 'STANDARD_IA'
                            },
                            {
                                'Days':
                                    settings.S3_BUCKET_LC_GLACIER_TRANSITION,
                                'StorageClass': 'GLACIER'
                            }
                        ]
                    }
                ]
            }
        )
