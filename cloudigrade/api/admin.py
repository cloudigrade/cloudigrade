"""Module to expose our models in Django admin."""
from django.contrib import admin

from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsInstanceEvent,
    AwsMachineImage,
)
from api.clouds.azure.models import (
    AzureCloudAccount,
    AzureInstance,
    AzureInstanceEvent,
    AzureMachineImage,
)
from api.models import (
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

admin.site.register(AzureCloudAccount)
admin.site.register(AzureMachineImage)
admin.site.register(AzureInstance)
admin.site.register(AzureInstanceEvent)
