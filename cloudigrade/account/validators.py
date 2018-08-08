"""DRF API validators for the account app."""
import datetime
import re

from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from account import AWS_PROVIDER_STRING

AWS_ACCOUNT_ID_SERIALIZER = serializers.CharField(max_length=12)


def validate_cloud_provider_account_id(data):
    """
    Validate cloud_account_id specifically for the cloud_provider.

    This validator presumes that as we expand support for more cloud providers
    we will need different serializers for each cloud's account ID format. In
    the case of AWS, we can enforce a 12-digit string. Other cloud providers
    likely have different rules, and as new clouds are added, we can expand
    this validator to be aware of those different rules.
    """
    cloud_account_id = data['cloud_account_id']
    try:
        if data['cloud_provider'] == AWS_PROVIDER_STRING:
            if re.match(r'\d{12}', cloud_account_id):
                cloud_account_id = AWS_ACCOUNT_ID_SERIALIZER.to_internal_value(
                    cloud_account_id)
            else:
                raise ValidationError()
        # More cloud-specific serializer checks to go here in 'elif' blocks.

        data['cloud_account_id'] = cloud_account_id
        return data
    except ValidationError as e:
        raise ValidationError(
            detail={
                'cloud_provider':
                _('Incorrect cloud_account_id type for cloud_provider "{0}"')
                .format(data['cloud_provider']),
                'cloud_account_id':
                e.detail,
            }
        )


def in_the_past(base):
    """
    Ensure the date is in the past or present, not the future.

    Args:
        base (datetime): some datetime to check

    Returns:
        datetime: base or "now" if base is in the future

    """
    now = datetime.datetime.now(tz=base.tzinfo)
    if now < base:
        return now
    return base
