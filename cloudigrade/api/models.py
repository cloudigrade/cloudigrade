"""Cloudigrade API v2 Models."""
import json
import logging

import model_utils
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _

from util.misc import get_now
from util.models import BaseGenericModel, BaseModel

logger = logging.getLogger(__name__)


class CloudAccount(BaseGenericModel):
    """Base Customer Cloud Account Model."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True, null=False,)
    name = models.CharField(max_length=256, null=False, db_index=True)
    is_enabled = models.BooleanField(null=False, default=True)

    # We must store the platform authentication_id in order to know things
    # like when to delete the Clount.
    # Unfortunately because of the way platform Sources is designed
    # we must also keep track of the source_id and the endpoint_id.
    # Why? see https://github.com/RedHatInsights/sources-api/issues/179
    platform_authentication_id = models.IntegerField(null=True)
    platform_endpoint_id = models.IntegerField(null=True)
    platform_source_id = models.IntegerField(null=True)

    class Meta:
        unique_together = ("user", "name")

    @property
    def cloud_account_id(self):
        """
        Get the external cloud provider's ID for this account.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_account_id

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_type

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"is_enabled='{self.is_enabled}', "
            f"user_id={self.user_id}, "
            f"platform_authentication_id={self.platform_authentication_id}, "
            f"platform_endpoint_id={self.platform_endpoint_id}, "
            f"platform_source_id={self.platform_source_id}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    @transaction.atomic
    def disable(self):
        """
        Mark this CloudAccount as disabled and perform operations to make it so.

        This has the side effect of finding all related powered-on instances and
        recording a new "power_off" event them. It also calls the related content_object
        (e.g. AwsCloudAccount) to make any cloud-specific changes.
        """
        if self.is_enabled:
            self.is_enabled = False
            self.save()
        self._power_off_instances(power_off_time=get_now())
        self.content_object.disable()

    def _power_off_instances(self, power_off_time):
        """
        Mark all running instances belonging to this CloudAccount as powered off.

        Args:
            power_off_time (datetime.datetime): time to set when stopping the instances
        """
        from api.util import recalculate_runs  # Avoid circular import.

        instances = self.instance_set.all()
        for instance in instances:
            last_event = (
                InstanceEvent.objects.filter(instance=instance)
                .order_by("-occurred_at")
                .first()
            )
            if last_event and last_event.event_type != InstanceEvent.TYPE.power_off:
                content_object_class = last_event.content_object.__class__
                cloud_specific_event = content_object_class.objects.create()
                event = InstanceEvent.objects.create(
                    event_type=InstanceEvent.TYPE.power_off,
                    occurred_at=power_off_time,
                    instance=instance,
                    content_object=cloud_specific_event,
                )
                recalculate_runs(event)


class MachineImage(BaseGenericModel):
    """Base model for a cloud VM image."""

    PENDING = "pending"
    PREPARING = "preparing"
    INSPECTING = "inspecting"
    INSPECTED = "inspected"
    ERROR = "error"
    UNAVAILABLE = "unavailable"  # images we can't access but know must exist
    STATUS_CHOICES = (
        (PENDING, "Pending Inspection"),
        (PREPARING, "Preparing for Inspection"),
        (INSPECTING, "Being Inspected"),
        (INSPECTED, "Inspected"),
        (ERROR, "Error"),
        (UNAVAILABLE, "Unavailable for Inspection"),
    )
    inspection_json = models.TextField(null=True, blank=True)
    is_encrypted = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=PENDING)
    rhel_detected_by_tag = models.BooleanField(default=False)
    openshift_detected = models.BooleanField(default=False)
    name = models.CharField(max_length=256, null=True, blank=True)

    @property
    def rhel(self):
        """
        Indicate if the image contains RHEL.

        Returns:
            bool: calculated using the `rhel_detected` property.

        """
        return self.rhel_detected

    @property
    def rhel_version(self):
        """
        Get the detected version of RHEL.

        Returns:
            str of the detected version or None if not set.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get("rhel_version", None)
        return None

    @property
    def rhel_enabled_repos_found(self):
        """
        Indicate if the image contains RHEL enabled repos.

        Returns:
            bool: Value of `rhel_enabled_repos_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get("rhel_enabled_repos_found", False)
        return False

    @property
    def rhel_product_certs_found(self):
        """
        Indicate if the image contains Red Hat product certs.

        Returns:
            bool: Value of `rhel_product_certs_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get("rhel_product_certs_found", False)
        return False

    @property
    def rhel_release_files_found(self):
        """
        Indicate if the image contains RHEL release files.

        Returns:
            bool: Value of `rhel_release_files_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get("rhel_release_files_found", False)
        return False

    @property
    def rhel_signed_packages_found(self):
        """
        Indicate if the image contains Red Hat signed packages.

        Returns:
            bool: Value of `rhel_signed_packages_found` from inspection_json.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get("rhel_signed_packages_found", False)
        return False

    @property
    def rhel_detected(self):
        """
        Indicate if the image detected RHEL.

        Returns:
            bool: combination of various image properties that results in our
                canonical definition of whether the image is marked for RHEL.

        """
        return (
            self.rhel_detected_by_tag
            or self.content_object.is_cloud_access
            or self.rhel_enabled_repos_found
            or self.rhel_product_certs_found
            or self.rhel_release_files_found
            or self.rhel_signed_packages_found
        )

    @property
    def syspurpose(self):
        """
        Get the detected system purpose (syspurpose).

        Returns:
            str of the detected system purpose or None if not set.

        """
        if self.inspection_json:
            image_json = json.loads(self.inspection_json)
            return image_json.get("syspurpose", None)
        return None

    @property
    def openshift(self):
        """
        Indicate if the image contains OpenShift.

        Returns:
            bool: the `openshift_detected` property.

        """
        return self.openshift_detected

    @property
    def cloud_image_id(self):
        """Get the external cloud provider's ID for this image."""
        return self.content_object.is_cloud_access

    @property
    def is_cloud_access(self):
        """Indicate if the image is provided by Red Hat Cloud Access."""
        return self.content_object.is_cloud_access

    @property
    def is_marketplace(self):
        """Indicate if the image is from AWS/Azure/GCP/etc. Marketplace."""
        return self.content_object.is_marketplace

    @property
    def cloud_type(self):
        """Get the external cloud provider type."""
        return self.content_object.cloud_type

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        name = str(repr(self.name)) if self.name is not None else None
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"name={name}, "
            f"status='{self.status}', "
            f"is_encrypted={self.is_encrypted}, "
            f"rhel_detected_by_tag={self.rhel_detected_by_tag}, "
            f"openshift_detected={self.openshift_detected}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Save this image and delete any related ConcurrentUsage objects."""
        concurrent_usages = ConcurrentUsage.objects.filter(
            potentially_related_runs__in=Run.objects.filter(machineimage=self)
        )
        concurrent_usages.delete()
        return super().save(*args, **kwargs)


class Instance(BaseGenericModel):
    """Base model for a compute/VM instance in a cloud."""

    cloud_account = models.ForeignKey(
        CloudAccount, on_delete=models.CASCADE, db_index=True, null=False,
    )
    machine_image = models.ForeignKey(
        MachineImage, on_delete=models.CASCADE, db_index=True, null=True,
    )

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        machine_image_id = (
            str(repr(self.machine_image_id))
            if self.machine_image_id is not None
            else None
        )
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"cloud_account_id={self.cloud_account_id}, "
            f"machine_image_id={machine_image_id}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_type

    @property
    def cloud_instance_id(self):
        """
        Get the external cloud instance id.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_instance_id


@receiver(post_delete, sender=Instance)
def instance_post_delete_callback(*args, **kwargs):
    """
    Delete the instance's machine image if no other instances use it.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    instance = kwargs["instance"]

    # When multiple instances are deleted at the same time django will
    # attempt to delete the machine image multiple times since instance
    # objects will no longer appear to be in the database.
    # Catch and log the raised DoesNotExist error from the additional
    # attempts to remove a machine image.
    try:
        if (
            instance.machine_image is not None
            and not Instance.objects.filter(machine_image=instance.machine_image)
            .exclude(id=instance.id)
            .exists()
        ):
            logger.info(
                _("%s is no longer used by any instances and will be deleted"),
                instance.machine_image,
            )
            instance.machine_image.delete()
    except MachineImage.DoesNotExist:
        logger.info(
            _("Machine image associated with instance %s has already been deleted."),
            instance,
        )


class InstanceEvent(BaseGenericModel):
    """Base model for an event triggered by a Instance."""

    TYPE = model_utils.Choices("power_on", "power_off", "attribute_change")
    instance = models.ForeignKey(
        Instance, on_delete=models.CASCADE, db_index=True, null=False,
    )
    event_type = models.CharField(max_length=32, choices=TYPE, null=False, blank=False,)
    occurred_at = models.DateTimeField(null=False)

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return self.content_object.cloud_type

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        occurred_at = (
            repr(self.occurred_at.isoformat()) if self.occurred_at is not None else None
        )
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"instance_id={self.instance_id}, "
            f"event_type={self.event_type}, "
            f"occurred_at=parse({occurred_at}), "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )


class Run(BaseModel):
    """Base model for a Run object."""

    start_time = models.DateTimeField(null=False)
    end_time = models.DateTimeField(blank=True, null=True)
    machineimage = models.ForeignKey(
        MachineImage, on_delete=models.CASCADE, db_index=True, null=True,
    )
    instance = models.ForeignKey(
        Instance, on_delete=models.CASCADE, db_index=True, null=False,
    )
    instance_type = models.CharField(max_length=64, null=True, blank=True)
    memory = models.FloatField(default=0, blank=True, null=True)
    vcpu = models.IntegerField(default=0, blank=True, null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Save this run and delete any related ConcurrentUsage objects."""
        concurrent_usages = ConcurrentUsage.objects.filter(
            potentially_related_runs=self
        )
        concurrent_usages.delete()
        return super().save(*args, **kwargs)


@receiver(pre_delete, sender=Run)
def run_pre_delete_callback(*args, **kwargs):
    """
    Delete any related ConcurrentUsage objects prior to deleting the run.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    run = kwargs["instance"]
    concurrent_usages = ConcurrentUsage.objects.filter(potentially_related_runs=run)
    concurrent_usages.delete()


class MachineImageInspectionStart(BaseModel):
    """Model to track any time an image starts inspection."""

    machineimage = models.ForeignKey(
        MachineImage, on_delete=models.CASCADE, db_index=True, null=False,
    )


class ConcurrentUsage(BaseModel):
    """Saved calculation of max concurrent usage for a date+user+account."""

    date = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True, null=False,)
    cloud_account = models.ForeignKey(
        CloudAccount, on_delete=models.CASCADE, db_index=True, null=True,
    )
    instances = models.IntegerField()
    _instances_list = models.TextField(
        db_column="instances_list", null=True, blank=True
    )
    memory = models.FloatField()
    vcpu = models.IntegerField()
    potentially_related_runs = models.ManyToManyField(Run)

    @property
    def instances_list(self):
        """Get instance list."""
        return json.loads(self._instances_list)

    @instances_list.setter
    def instances_list(self, value):
        """Set instance list."""
        self._instances_list = json.dumps(value)

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        date = repr(self.date.isoformat()) if self.date is not None else None
        created_at = (
            repr(self.created_at.isoformat()) if self.created_at is not None else None
        )
        updated_at = (
            repr(self.updated_at.isoformat()) if self.updated_at is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"date={date}, "
            f"user_id={self.user_id}, "
            f"cloud_account_id={self.cloud_account_id}, "
            f"memory={self.memory}, "
            f"vcpu={self.vcpu}, "
            f"created_at={created_at}, "
            f"updated_at={updated_at}"
            f")"
        )
