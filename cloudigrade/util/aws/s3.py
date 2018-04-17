"""Helper utility module to wrap up common AWS S3 operations."""
import gzip
import logging

import boto3
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def get_object_content_from_s3(bucket, key, compression='gzip'):
    """
    Get the file contents from an S3 object.

    Args:
        bucket (str): The S3 bucket the object is stored in.
        key (str): The S3 object key identified.
        compression (str): The compression format for the stored file object.

    Returns:
        str: The string contents of the file object.

    """
    content = None
    region = settings.S3_DEFAULT_REGION
    s3_object = boto3.resource('s3', region_name=region).Object(bucket, key)

    object_bytes = s3_object.get()['Body'].read()

    if compression == 'gzip':
        content = gzip.decompress(object_bytes).decode('utf-8')
    elif compression is None:
        content = object_bytes.decode('utf-8')
    else:
        logger.error(_('Unsupported compression format'))

    return content
