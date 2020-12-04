"""Internal views for cloudigrade API."""
from django_filters import rest_framework as django_filters
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, schema
from rest_framework.response import Response

from api import models, serializers
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


class InternalMachineImageViewSet(viewsets.ReadOnlyModelViewSet):
    """Retrieve, reinspect, or list MachineImages."""

    schema = None
    serializer_class = serializers.MachineImageSerializer
    queryset = models.MachineImage.objects.all()
    filter_backends = [django_filters.DjangoFilterBackend]

    @action(detail=True, methods=["post"])
    def reinspect(self, request, pk=None):
        """Set the machine image status to pending, so it gets reinspected."""
        machine_image = self.get_object()
        machine_image.status = models.MachineImage.PENDING
        machine_image.save()

        serializer = serializers.MachineImageSerializer(
            machine_image, context={"request": request}
        )

        return Response(serializer.data)
