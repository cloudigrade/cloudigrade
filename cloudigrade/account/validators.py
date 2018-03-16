"""DRF API validators for the account app."""
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from account import AWS_PROVIDER_STRING

AWS_ACCOUNT_ID_SERIALIZER = serializers.DecimalField(
    max_digits=12, decimal_places=0
)


def validate_cloud_provider_account_id(data):
    """
    Validate cloud_account_id specifically for the cloud_provider.

    This validator presumes that as we expand support for more cloud providers
    we will need different serializers for each cloud's account ID format. In
    the case of AWS, we can enforce a 12-digit decimal. Other cloud providers
    likely have different rules, and as new clouds are added, we can expand
    this validator to be aware of those different rules.
    """
    cloud_account_id = data['cloud_account_id']
    try:
        if data['cloud_provider'] == AWS_PROVIDER_STRING:
            cloud_account_id = AWS_ACCOUNT_ID_SERIALIZER.to_internal_value(
                cloud_account_id
            )
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
