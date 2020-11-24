"""Internal views for cloudigrade API."""
from rest_framework import exceptions, status
from rest_framework.decorators import api_view, authentication_classes, schema
from rest_framework.response import Response

from api.authentication import ThreeScaleAuthenticationNoOrgAdmin
from api.models import CloudAccount


@api_view(["POST"])
@authentication_classes([ThreeScaleAuthenticationNoOrgAdmin])
@schema(None)
def availability_check(request):
    """
    Attempt to re-enable cloudigrade accounts with matching source_id.

    This is an internal only API, so we do not want it to be in the openapi.spec.
    """
    data = request.data
    source_id = data.get("source_id")
    if not source_id:
        raise exceptions.ValidationError(detail="source_id field is required")

    cloudaccounts = CloudAccount.objects.filter(platform_source_id=source_id)
    for cloudaccount in cloudaccounts:
        cloudaccount.enable()

    return Response(status=status.HTTP_204_NO_CONTENT)
