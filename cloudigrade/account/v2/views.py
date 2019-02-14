"""DRF API views for the account app v2."""
import logging

from account.v2.authentication import ThreeScaleAuthentication
from account.views import SysconfigViewSet

logger = logging.getLogger(__name__)


class SysconfigViewSetV2(SysconfigViewSet):
    """View to display our cloud account ids."""

    authentication_classes = (ThreeScaleAuthentication, )
