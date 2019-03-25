"""DRF API views for the account app v2."""
from account import views as v1_views
from account.v2 import serializers
from account.v2.authentication import ThreeScaleAuthentication


class AccountViewSet(v1_views.AccountViewSet):
    """
    Create, retrieve, update, delete, or list customer accounts.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication, )
    serializer_class = serializers.AccountPolymorphicSerializer


class InstanceViewSet(v1_views.InstanceViewSet):
    """
    List all or retrieve a single instance.

    Authenticate via 3scale.
    Do not allow to create, update, replace, or delete an instance at
    this view because we currently **only** allow instances to be retrieved.
    """

    authentication_classes = (ThreeScaleAuthentication, )
    serializer_class = serializers.InstancePolymorphicSerializer


class MachineImageViewSet(v1_views.MachineImageViewSet):
    """
    List all, retrieve, or update a single machine image.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication, )
    serializer_class = serializers.MachineImagePolymorphicSerializer


class SysconfigViewSet(v1_views.SysconfigViewSet):
    """
    View to display our cloud account ids.

    Authenticate via 3scale.
    """

    authentication_classes = (ThreeScaleAuthentication, )
