"""Helper utility module to wrap up common AWS S3 operations."""
import gzip
import logging

import boto3
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def get_object_content_from_s3(bucket, key):
    """
    Get the file contents from an S3 object.

    Args:
        bucket (str): The S3 bucket the object is stored in.
        key (str): The S3 object key identified.

    Returns:
        str: The string contents of the file object.

    """
    region = settings.S3_DEFAULT_REGION
    s3_object = boto3.resource('s3', region_name=region).Object(bucket, key)
    s3_object = s3_object.get()

    object_bytes = s3_object['Body'].read()

    try:
        if s3_object.get('ContentType', None) == 'application/x-gzip':
            content = gzip.decompress(object_bytes).decode('utf-8')
        else:
            content = object_bytes.decode('utf-8')
    except UnicodeDecodeError as ex:
        logger.exception(_('Failed to decode content of {key}: {error}')
                         .format(key=key, error=ex))
        raise

    return content
