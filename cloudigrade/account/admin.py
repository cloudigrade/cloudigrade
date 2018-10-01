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


class AccountAdmin(admin.ModelAdmin):
    """Admin model of Account."""

    list_display = (
        'id',
        'name',
        'user',
        'user_id',
    )


class InstanceAdmin(admin.ModelAdmin):
    """Admin model of Instance."""

    list_display = (
        'id',
        'account',
    )


class InstanceEventAdmin(admin.ModelAdmin):
    """Admin model of InstanceEvent."""

    list_display = (
        'id',
        'instance',
        'machineimage',
        'event_type',
        'occurred_at',
    )


class MachineImageAdmin(admin.ModelAdmin):
    """Admin model of MachineImage."""

    list_display = (
        'id',
        'name',
        'status',
    )


class AwsAccountAdmin(admin.ModelAdmin):
    """Admin model of AwsAccount."""

    list_display = AccountAdmin.list_display + (
        'aws_account_id',
        'account_arn',
    )


class AwsInstanceAdmin(admin.ModelAdmin):
    """Admin model of AwsInstance."""

    list_display = InstanceAdmin.list_display + (
        'ec2_instance_id',
        'region',
    )


class AwsInstanceEventAdmin(admin.ModelAdmin):
    """Admin model of AwsInstanceEvent."""

    list_display = InstanceEventAdmin.list_display + (
        'subnet',
        'instance_type',
    )


class AwsMachineImageAdmin(admin.ModelAdmin):
    """Admin model of AwsMachineImage."""

    list_display = MachineImageAdmin.list_display + (
        'ec2_ami_id',
        'platform',
        'owner_aws_account_id',
        'rhel_challenged',
        'openshift_challenged',
    )


admin.site.register(Account, AccountAdmin)
admin.site.register(Instance, InstanceAdmin)
admin.site.register(InstanceEvent, InstanceEventAdmin)
admin.site.register(MachineImage, MachineImageAdmin)

admin.site.register(AwsAccount, AwsAccountAdmin)
admin.site.register(AwsInstance, AwsInstanceAdmin)
admin.site.register(AwsInstanceEvent, AwsInstanceEventAdmin)
admin.site.register(AwsMachineImage, AwsMachineImageAdmin)
