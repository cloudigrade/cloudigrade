"""Module to expose our models in Django admin."""
from django.contrib import admin

from account.models import (Account,
                            AwsAccount,
                            AwsInstance,
                            AwsInstanceEvent,
                            AwsMachineImage,
                            Instance,
                            InstanceEvent,
                            MachineImage)

admin.site.register(Account, admin.ModelAdmin)
admin.site.register(Instance, admin.ModelAdmin)
admin.site.register(InstanceEvent, admin.ModelAdmin)
admin.site.register(MachineImage, admin.ModelAdmin)

admin.site.register(AwsAccount, admin.ModelAdmin)
admin.site.register(AwsInstance, admin.ModelAdmin)
admin.site.register(AwsInstanceEvent, admin.ModelAdmin)
admin.site.register(AwsMachineImage, admin.ModelAdmin)
