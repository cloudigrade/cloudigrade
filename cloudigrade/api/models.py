"""Cloudigrade API v2 Models."""
import json
import logging

import model_utils
from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _
from django_prometheus.models import ExportModelOperationsMixin

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from util.misc import get_now, get_today, lock_task_for_user_ids
from util.models import BaseGenericModel, BaseModel

logger = logging.getLogger(__name__)


class UserTaskLock(BaseModel):
    """Model used to lock running tasks for a user."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, db_index=True, null=False
    )
    locked = models.BooleanField(default=False, null=False)


class CloudAccount(ExportModelOperationsMixin("CloudAccount"), BaseGenericModel):
    """Base Customer Cloud Account Model."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    name = models.CharField(max_length=256, null=False, db_index=True)
    is_enabled = models.BooleanField(null=False, default=True)
    enabled_at = models.DateTimeField(auto_now_add=True)

    # We must store the platform authentication_id in order to know things
    # like when to delete the Clount.
    # Unfortunately because of the way platform Sources is designed
    # we must also keep track of the source_id and application_id.
    # Why? see https://github.com/RedHatInsights/sources-api/issues/179
    platform_authentication_id = models.IntegerField()
    platform_application_id = models.IntegerField()
    platform_source_id = models.IntegerField()

    class Meta:
        unique_together = (
            ("user", "name"),
            ("platform_authentication_id", "platform_application_id"),
        )

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
        enabled_at = (
            repr(self.enabled_at.isoformat()) if self.enabled_at is not None else None
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
            f"name='{self.name}', "
            f"is_enabled='{self.is_enabled}', "
            f"enabled_at=parse({enabled_at}), "
            f"user_id={self.user_id}, "
            f"platform_authentication_id={self.platform_authentication_id}, "
            f"platform_application_id={self.platform_application_id}, "
            f"platform_source_id={self.platform_source_id}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    @transaction.atomic
    def enable(self):
        """
        Mark this CloudAccount as enabled and perform operations to make it so.

        This has the side effect of calling the related content_object (e.g.
        AwsCloudAccount) to make any cloud-specific changes. If any that cloud-specific
        function fails, we rollback our state change and re-raise the exception for the
        caller to handle further.
        """
        logger.info(
            _("'is_enabled' is %(is_enabled)s before enabling %(cloudaccount)s"),
            {"is_enabled": self.is_enabled, "cloudaccount": self},
        )
        if not self.is_enabled:
            self.is_enabled = True
            self.enabled_at = get_now()
            self.save()
        try:
            self.content_object.enable()
            # delete stale ConcurrentUsage when an clount is enabled
            ConcurrentUsage.objects.filter(user=self.user, date=get_today()).delete()
        except Exception as e:
            # All failure notifications should happen during the failure
            logger.info(e)
            transaction.set_rollback(True)
            return False

        from cloudigrade.api.tasks import notify_application_availability_task

        notify_application_availability_task.delay(
            self.platform_application_id, "available"
        )

    @transaction.atomic
    def disable(self, message="", power_off_instances=True, notify_sources=True):
        """
        Mark this CloudAccount as disabled and perform operations to make it so.

        This has the side effect of finding all related powered-on instances and
        recording a new "power_off" event them. It also calls the related content_object
        (e.g. AwsCloudAccount) to make any cloud-specific changes.

        Args:
            message (string): status message to set on the Sources Application
            power_off_instances (bool): if this is set to false, we do not create
                power_off instance events when disabling the account. This is used on
                account deletion, when we still want to run the rest of the account
                disable logic, but should not be creating power_off instance events.
                Since creating the instance event in the same transaction as deleting
                the account causes Django errors.
            notify_sources (bool): determines if we notify sources about this operation.
                This should always be true except for very special cases.
        """
        logger.info(_("Attempting to disable %(account)s"), {"account": self})
        if self.is_enabled:
            self.is_enabled = False
            self.save()
        if power_off_instances:
            self._power_off_instances(power_off_time=get_now())
        self.content_object.disable()
        if notify_sources:
            from cloudigrade.api.tasks import notify_application_availability_task

            notify_application_availability_task.delay(
                self.platform_application_id, "unavailable", message
            )
        logger.info(_("Finished disabling %(account)s"), {"account": self})

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


@receiver(pre_delete, sender=CloudAccount)
def cloud_account_pre_delete_callback(*args, **kwargs):
    """
    Disable CloudAccount before deleting it.

    This runs the logic to notify sources of application availability.
    This additionally runs the cloud specific disable function with the
    power_off_instances set to False.

    Note: Signal receivers must accept keyword arguments (**kwargs).

    Note: Django does *not* (as of 3.0 at the time of this writing) lock the sender
    instance for deletion when the pre_delete signal fires. This means another request
    could fetch and attempt to alter the same instance while this function is running,
    and bad things could happen. See also api.tasks.delete_from_sources_kafka_message.
    """
    instance = kwargs["instance"]
    try:
        instance.refresh_from_db()
        instance.disable(power_off_instances=False)
    except CloudAccount.DoesNotExist:
        logger.info(
            _(
                "Cloud Account %s is already deleted inside pre_delete signal. "
                "This should not happen."
            ),
            instance,
        )


@receiver(post_delete, sender=CloudAccount)
def cloud_account_post_delete_callback(*args, **kwargs):
    """
    Delete the User, if this is the last cloudaccount owned by the User.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    instance = kwargs["instance"]

    # When multiple clounts are deleted at the same time django will
    # attempt to delete the user multiple times.
    # Catch and log the raised DoesNotExist error from the additional
    # attempts.
    try:
        if (
            not CloudAccount.objects.filter(user=instance.user)
            .exclude(id=instance.id)
            .exists()
        ):
            logger.info(
                _("%s no longer has any more cloud accounts and will be deleted"),
                instance.user,
            )
            instance.user.delete()
    except User.DoesNotExist:
        logger.info(_("User for clount id %s has already been deleted."), instance.id)


class MachineImage(ExportModelOperationsMixin("MachineImage"), BaseGenericModel):
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
    architecture = models.CharField(max_length=32, null=True, blank=True)

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
            f"name={repr(name)}, "
            f"status={repr(self.status)}, "
            f"is_encrypted={self.is_encrypted}, "
            f"rhel_detected_by_tag={self.rhel_detected_by_tag}, "
            f"openshift_detected={self.openshift_detected}, "
            f"architecture={repr(self.architecture)}, "
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
        if concurrent_usages.exists():
            # Lock all users that depend on this machineimage
            user_ids = set(
                Instance.objects.filter(machine_image=self).values_list(
                    "cloud_account__user__id", flat=True
                )
            )

            with lock_task_for_user_ids(user_ids):
                logger.info(
                    "Removing %(num_usages)d related ConcurrentUsage objects "
                    "related to Run %(run)s.",
                    {"num_usages": concurrent_usages.count(), "run": str(self)},
                )
                concurrent_usages.delete()
        return super().save(*args, **kwargs)


class Instance(ExportModelOperationsMixin("Instance"), BaseGenericModel):
    """Base model for a compute/VM instance in a cloud."""

    cloud_account = models.ForeignKey(
        CloudAccount,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    machine_image = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
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
        Instance,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    event_type = models.CharField(
        max_length=32,
        choices=TYPE,
        null=False,
        blank=False,
    )
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
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=True,
    )
    instance = models.ForeignKey(
        Instance,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )
    instance_type = models.CharField(max_length=64, null=True, blank=True)
    memory = models.FloatField(default=0, blank=True, null=True)
    vcpu = models.IntegerField(default=0, blank=True, null=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        """Save this run and delete any related ConcurrentUsage objects."""
        super().save(*args, **kwargs)
        concurrent_usages = ConcurrentUsage.objects.filter(
            potentially_related_runs=self
        )
        logger.info(
            "Removing %(num_usages)d related ConcurrentUsage objects "
            "related to Run %(run)s.",
            {"num_usages": concurrent_usages.count(), "run": str(self)},
        )
        concurrent_usages.delete()

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        start_time = (
            repr(self.start_time.isoformat()) if self.start_time is not None else None
        )
        end_time = (
            repr(self.end_time.isoformat()) if self.end_time is not None else None
        )

        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"machineimage={self.machineimage_id}, "
            f"instance={self.instance_id}, "
            f"instance_type={self.instance_type}, "
            f"memory={self.memory}, "
            f"vcpu={self.vcpu}, "
            f"start_time=parse({start_time}), "
            f"end_time=parse({end_time})"
            f")"
        )


@receiver(pre_delete, sender=Run)
def run_pre_delete_callback(*args, **kwargs):
    """
    Delete any related ConcurrentUsage prior to deleting the Run.

    This must be pre_delete not post_delete because the ManyToMany relationship's
    "through" table row may have already deleted by post_delete, and that leaves us no
    way to find the related ConcurrentUsage.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    run = kwargs["instance"]
    concurrent_usages = ConcurrentUsage.objects.filter(potentially_related_runs=run)
    concurrent_usages.delete()


class MachineImageInspectionStart(BaseModel):
    """Model to track any time an image starts inspection."""

    machineimage = models.ForeignKey(
        MachineImage,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )


class ConcurrentUsage(ExportModelOperationsMixin("ConcurrentUsage"), BaseModel):
    """Saved calculation of max concurrent usage for a date+user."""

    date = models.DateField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    _maximum_counts = models.TextField(db_column="maximum_counts", default="[]")
    potentially_related_runs = models.ManyToManyField(Run)

    class Meta:
        unique_together = (("date", "user"),)

    @property
    def maximum_counts(self):
        """Get maximum_counts list."""
        return json.loads(self._maximum_counts)

    @maximum_counts.setter
    def maximum_counts(self, value):
        """Set maximum_counts list."""
        self._maximum_counts = json.dumps(value)

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
            f"created_at={created_at}, "
            f"updated_at={updated_at}"
            f")"
        )


class ConcurrentUsageCalculationTask(
    ExportModelOperationsMixin("ConcurrentUsageTask"), BaseModel
):
    """Model for tracking concurrent usage tasks."""

    SCHEDULED = "SCHEDULED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    CANCELED = "CANCELED"
    ERROR = "ERROR"

    STATUS_CHOICES = (
        (SCHEDULED, "Task has been scheduled"),
        (RUNNING, "Task is running"),
        (COMPLETE, "Task is completed"),
        (CANCELED, "Task is canceled"),
        (ERROR, "Task has encountered an error"),
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=SCHEDULED)

    task_id = models.TextField(unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_index=True)
    date = models.DateField(db_index=True)

    def _revoke(self):
        """
        Revoke the Celery task.

        Generally, you should use cancel instead of this function. This isolated
        function exists only to support the delete callback because the task object
        itself may not actually exist and the save call in the cancel function would
        fail.
        """
        logger.info(
            "Revoking task to calculate concurrent usage for user_id: "
            "%(user_id)s and date: %(date)s. This task will be marked as canceled."
            % {"user_id": self.user.id, "date": self.date}
        )
        from celery import current_app

        current_app.control.revoke(self.task_id)

    def cancel(self):
        """Revokes the task if it is not currently running."""
        self._revoke()
        self.status = self.CANCELED
        self.save()

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
            f"task_id={self.task_id}, "
            f"status={self.status}, "
            f"created_at={created_at}, "
            f"updated_at={updated_at}"
            f")"
        )


@receiver(post_delete, sender=ConcurrentUsageCalculationTask)
def concurrentusagecalculationtask_post_delete_callback(*args, **kwargs):
    """
    Revoke the Celery task upon deleting ConcurrentUsageCalculationTask.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    calculation_task = kwargs["instance"]
    calculation_task._revoke()


class InstanceDefinition(BaseModel):
    """
    Lookup table for cloud provider instance definitions.

    Data should be retrieved from this table using the helper function
    get_instance_type_definition.
    """

    AWS = AWS_PROVIDER_STRING
    AZURE = AZURE_PROVIDER_STRING
    CLOUD_TYPE_CHOICES = (
        (AWS, "AWS EC2 instance definitions."),
        (AZURE, "Azure VM instance definitions."),
    )

    instance_type = models.CharField(
        max_length=256, null=False, blank=False, db_index=True
    )
    memory = models.IntegerField(default=0)
    vcpu = models.IntegerField(default=0)
    json_definition = models.JSONField()
    cloud_type = models.CharField(
        max_length=32, choices=CLOUD_TYPE_CHOICES, null=False, blank=False
    )

    class Meta:
        unique_together = (("instance_type", "cloud_type"),)
