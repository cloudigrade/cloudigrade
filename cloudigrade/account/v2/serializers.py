"""DRF API serializers for the account app v2."""
from rest_framework import serializers
from rest_polymorphic.serializers import PolymorphicSerializer

from account import serializers as v1_serializers
from account.models import (AwsAccount,
                            AwsInstance,
                            AwsMachineImage)


class AwsAccountSerializer(v1_serializers.AwsAccountSerializer):
    """Serialize a customer AwsAccount for API v2."""

    url = serializers.HyperlinkedIdentityField(
        view_name='v2-account-detail'
    )


class AccountPolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all account types."""

    model_serializer_mapping = {
        AwsAccount: AwsAccountSerializer,
    }


class AwsInstanceSerializer(v1_serializers.AwsInstanceSerializer):
    """Serialize a customer AwsInstance for API v2."""

    account = serializers.HyperlinkedIdentityField(
        view_name='v2-account-detail'
    )
    machineimage = serializers.HyperlinkedIdentityField(
        view_name='v2-machineimage-detail'
    )
    url = serializers.HyperlinkedIdentityField(
        view_name='v2-instance-detail'
    )


class InstancePolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all instance types."""

    model_serializer_mapping = {
        AwsInstance: AwsInstanceSerializer,
    }


class AwsMachineImageSerializer(v1_serializers.AwsMachineImageSerializer):
    """Serialize a customer AwsMachineImage for API v2."""

    url = serializers.HyperlinkedIdentityField(
        view_name='v2-machineimage-detail'
    )


class MachineImagePolymorphicSerializer(PolymorphicSerializer):
    """Combined polymorphic serializer for all image types."""

    model_serializer_mapping = {
        AwsMachineImage: AwsMachineImageSerializer,
    }
