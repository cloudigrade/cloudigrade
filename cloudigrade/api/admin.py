"""Module to expose our models in Django admin."""
from django.contrib import admin

from api.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
    CloudAccount,
    Instance,
    InstanceEvent,
    MachineImage,
)

admin.site.register(CloudAccount)
admin.site.register(MachineImage)
admin.site.register(Instance)
admin.site.register(InstanceEvent)

admin.site.register(AwsCloudAccount)
admin.site.register(AwsMachineImage)
admin.site.register(AwsInstance)
admin.site.register(AwsInstanceEvent)
