"""Module to expose our models in Django admin."""
from django.contrib import admin

from api.clouds.aws.models import (
    AwsCloudAccount,
    AwsInstance,
    AwsMachineImage,
)
from api.clouds.azure.models import AzureCloudAccount
from api.models import (
    CloudAccount,
    Instance,
    MachineImage,
)

admin.site.register(CloudAccount)
admin.site.register(MachineImage)
admin.site.register(Instance)

admin.site.register(AwsCloudAccount)
admin.site.register(AwsMachineImage)
admin.site.register(AwsInstance)

admin.site.register(AzureCloudAccount)
