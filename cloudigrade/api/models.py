"""Cloudigrade API v2 Models."""
import logging
import uuid
from datetime import timedelta

import model_utils
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core import validators
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext as _

from api import AWS_PROVIDER_STRING, AZURE_PROVIDER_STRING
from util.misc import get_now, lock_task_for_user_ids
from util.models import BaseGenericModel, BaseModel

logger = logging.getLogger(__name__)


class UserManager(BaseUserManager):
    """Manager class for the Api User model."""

    def create_user(
        self,
        account_number=None,
        org_id=None,
        password=None,
        date_joined=None,
        is_active=True,
        is_superuser=False,
        is_permanent=False,
    ):
        """create_user creates a user, requires at least an account_number or org_id."""
        if not account_number and not org_id:
            raise ValueError("Users must have at least an account_number or org_id")

        user = self.model(account_number=account_number, org_id=org_id)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        if date_joined:
            user.date_joined = date_joined

        user.is_active = is_active
        user.is_superuser = is_superuser
        user.is_permanent = is_permanent
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    """Class for our Api User model."""

    def user_uuid():
        """Return a UUID string to use for newly created Api users."""
        return str(uuid.uuid4())

    uuid = models.TextField(
        verbose_name="User Unique Id",
        max_length=150,
        unique=True,
        blank=False,
        default=user_uuid,
    )
    account_number = models.TextField(
        db_index=True,
        verbose_name="Account Number",
        max_length=150,
        unique=True,
        null=True,
    )
    org_id = models.TextField(
        db_index=True, verbose_name="Org Id", max_length=150, unique=True, null=True
    )
    is_active = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    is_permanent = models.BooleanField(default=False)
    date_joined = models.DateTimeField(verbose_name="Date Joined", default=now)

    objects = UserManager()

    USERNAME_FIELD = "uuid"
    REQUIRED_FIELDS = []

    class Meta:
        app_label = "api"

    def __str__(self):
        """Return the friendly string representation for the Api User."""
        return (
            f"{self.__class__.__name__}("
            f"id={self.id}, "
            f"uuid={self.uuid}, "
            f"account_number={self.account_number}, "
            f"org_id={self.org_id}, "
            f"is_permanent={self.is_permanent}, "
            f"date_joined={self.date_joined}"
            f")"
        )

    def delete(self, force=False):
        """Only delete a user if not permanent or force is True."""
        if force is False and self.is_permanent:
            return 0, {}
        return super(User, self).delete()


class UserTaskLock(BaseModel):
    """Model used to lock running tasks for a user."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, db_index=True, null=False
    )
    locked = models.BooleanField(default=False, null=False)


class CloudAccount(BaseGenericModel):
    """Base Customer Cloud Account Model."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_index=True,
        null=False,
    )

    # New CloudAccount instances are created with is_enabled=False because we must rely
    # on the enable method to determine if is_enabled can be True and update if so.
    is_enabled = models.BooleanField(null=False, default=False)
    enabled_at = models.DateTimeField(null=True, blank=True)

    # We must store the platform authentication_id in order to know things
    # like when to delete the CloudAccount.
    # Unfortunately because of the way platform Sources is designed
    # we must also keep track of the source_id and application_id.
    # Why? see https://github.com/RedHatInsights/sources-api/issues/179
    platform_authentication_id = models.IntegerField()
    platform_application_id = models.IntegerField()
    platform_source_id = models.IntegerField()

    # The related Application has its own pause/resume functionality that is orthogonal
    # to our is_enabled state. We must track the external paused state and combine it
    # with our is_enabled state to determine when we should or should not process new
    # data for this CloudAccount.
    platform_application_is_paused = models.BooleanField(null=False, default=False)

    # Some CloudAccounts are created synthetically for internal testing without any
    # real corresponding objects in external services like sources-api. We need to know
    # if that's true so we can bypass various operations that would expect valid
    # responses from interacting with those external services.
    is_synthetic = models.BooleanField(default=False)

    class Meta:
        unique_together = (("platform_authentication_id", "platform_application_id"),)

    @property
    def cloud_account_id(self):
        """
        Get the external cloud provider's ID for this account.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return getattr(self.content_object, "cloud_account_id", None)

    @property
    def cloud_type(self):
        """
        Get the external cloud provider type.

        This should be treated like an abstract method, but we can't actually
        extend ABC here because it conflicts with Django's Meta class.
        """
        return getattr(self.content_object, "cloud_type", None)

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
            f"is_enabled='{self.is_enabled}', "
            f"enabled_at=parse({enabled_at}), "
            f"user_id={self.user_id}, "
            f"platform_authentication_id={self.platform_authentication_id}, "
            f"platform_application_id={self.platform_application_id}, "
            f"platform_application_is_paused={self.platform_application_is_paused}, "
            f"platform_source_id={self.platform_source_id}, "
            f"is_synthetic={self.is_synthetic}, "
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    def enable(self, disable_upon_failure=True):
        """
        Mark this CloudAccount as enabled and perform operations to make it so.

        Setting "is_enabled" to True here means that we start accepting and recording
        any new activity from the cloud (e.g. via CloudTrail for AWS), and we may also
        perform a full describe of the cloud account to capture the current state.

        This has the side effect of calling the related content_object (e.g.
        AwsCloudAccount) to make any cloud-specific changes. If any that cloud-specific
        function fails, we rollback our state change and re-raise the exception for the
        caller to handle further.

        If we fail to enable the account (for example, if cloud-specific permissions
        checks fail), this function automatically calls `disable` to ensure that our
        internal state is correctly reflected.
        """
        logger.info(
            _("'is_enabled' is %(is_enabled)s before enabling %(cloudaccount)s"),
            {"is_enabled": self.is_enabled, "cloudaccount": self},
        )
        previously_enabled = self.is_enabled
        enabled_successfully = False
        with transaction.atomic():
            if not previously_enabled:
                self.is_enabled = True
                self.enabled_at = get_now()
                self.save()
            try:
                enabled_successfully = self.content_object.enable()
            except Exception as e:
                logger.info(e)
            finally:
                if not enabled_successfully:
                    transaction.set_rollback(True)

        if enabled_successfully and not self.is_synthetic:
            from api.tasks.sources import notify_application_availability_task

            logger.info(
                _(
                    "Enabled CloudAccount %(id)s and will notify sources "
                    "(%(account_number)s, %(org_id)s, %(application_id)s)"
                ),
                {
                    "id": self.id,
                    "account_number": self.user.account_number,
                    "org_id": self.user.org_id,
                    "application_id": self.platform_application_id,
                },
            )
            notify_application_availability_task.delay(
                self.user.account_number,
                self.user.org_id,
                self.platform_application_id,
                "available",
            )
        elif disable_upon_failure and not previously_enabled:
            # We do not need to notify sources when calling self.disable() here because
            # self.content_object.enable() should have already notified with its error.
            logger.info(
                _("Failed to enable CloudAccount %(id)s; explicitly disabling."),
                {"id": self.id},
            )
            self.disable(notify_sources=False)

        if enabled_successfully:
            logger.info(
                _("CloudAccount %(id)s was enabled successfully"), {"id": self.id}
            )
        else:
            logger.info(
                _("CloudAccount %(id)s was not enabled successfully"), {"id": self.id}
            )
        return enabled_successfully

    @transaction.atomic
    def disable(self, message="", notify_sources=True):
        """
        Mark this CloudAccount as disabled and perform operations to make it so.

        Setting "is_enabled" to False here means that we have stopped accepting and
        recording any new activity from the cloud (e.g. via CloudTrail for AWS).

        This has the side effect of finding all related powered-on instances and
        recording a new "power_off" event them. It also calls the related content_object
        (e.g. AwsCloudAccount) to make any cloud-specific changes.

        Args:
            message (string): status message to set on the Sources Application
            notify_sources (bool): determines if we notify sources about this operation.
                This should always be true except for very special cases.
        """
        logger.info(_("Attempting to disable %(account)s"), {"account": self})
        if self.is_enabled:
            self.is_enabled = False
            self.save()
        if self.content_object:
            self.content_object.disable()
        else:
            logger.error(
                _(
                    "content_object is missing and cannot completely disable "
                    "%(cloud_account)s"
                ),
                {"cloud_account": self},
            )
        if notify_sources and not self.is_synthetic:
            from api.tasks.sources import notify_application_availability_task

            notify_application_availability_task.delay(
                self.user.account_number,
                self.user.org_id,
                self.platform_application_id,
                "unavailable",
                message,
            )
        logger.info(_("Finished disabling %(account)s"), {"account": self})


@receiver(pre_delete, sender=CloudAccount)
def cloud_account_pre_delete_callback(*args, **kwargs):
    """
    Disable CloudAccount before deleting it.

    This runs the logic to notify sources of application availability.

    Note: Signal receivers must accept keyword arguments (**kwargs).

    Note: Django does *not* (as of 3.0 at the time of this writing) lock the sender
    instance for deletion when the pre_delete signal fires. This means another request
    could fetch and attempt to alter the same instance while this function is running,
    and bad things could happen. See also api.tasks.delete_from_sources_kafka_message.
    """
    instance = kwargs["instance"]
    try:
        instance.refresh_from_db()
        instance.disable()
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

    # When multiple cloud accounts are deleted at the same time django will
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
        logger.info(
            _("User for cloud account id %s has already been deleted."), instance.id
        )


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
    TERMINAL_STATUSES = (INSPECTED, ERROR, UNAVAILABLE)

    inspection_json = models.TextField(null=True, blank=True)
    is_encrypted = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=PENDING)
    rhel_detected_by_tag = models.BooleanField(default=False)
    openshift_detected = models.BooleanField(default=False)
    name = models.CharField(max_length=256, null=True, blank=True)
    architecture = models.CharField(max_length=32, null=True, blank=True)

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


class Instance(BaseGenericModel):
    """Base model for a compute/VM instance in a cloud."""

    # Placeholder fields while breaking foreign keys for database cleanup.
    cloud_account_id = models.IntegerField(db_index=False, null=True)
    machine_image_id = models.IntegerField(db_index=False, null=True)

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
    # Placeholder field while breaking foreign keys for database cleanup.
    instance_id = models.IntegerField(db_index=False, null=True)
    event_type = models.CharField(
        max_length=32,
        choices=TYPE,
        null=False,
        blank=False,
    )
    occurred_at = models.DateTimeField(null=False, db_index=True)

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

    start_time = models.DateTimeField(null=False, db_index=True)
    end_time = models.DateTimeField(blank=True, null=True, db_index=True)

    # Placeholder fields while breaking foreign keys for database cleanup.
    machineimage_id = models.IntegerField(db_index=False, null=True)
    instance_id = models.IntegerField(db_index=False, null=True)

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
        if concurrent_usages_count := concurrent_usages.count():
            logger.info(
                "Removing %(num_usages)d related ConcurrentUsage objects "
                "related to Run %(run)s.",
                {"num_usages": concurrent_usages_count, "run": str(self)},
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

    # Placeholder fields while breaking foreign keys for database cleanup.
    machineimage_id = models.IntegerField(db_index=False, null=True)


class ConcurrentUsage(BaseModel):
    """Saved calculation of max concurrent usage for a date+user."""

    date = models.DateField(db_index=True)

    # Placeholder fields while breaking foreign keys for database cleanup.
    user_id = models.IntegerField(db_index=False, null=True)

    _maximum_counts = models.TextField(db_column="maximum_counts", default="[]")
    potentially_related_runs = models.ManyToManyField(Run)

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
    memory_mib = models.IntegerField(default=0)  # MiB to be precise.
    vcpu = models.DecimalField(max_digits=32, decimal_places=2, default=0.00)
    json_definition = models.JSONField()
    cloud_type = models.CharField(
        max_length=32, choices=CLOUD_TYPE_CHOICES, null=False, blank=False
    )

    class Meta:
        unique_together = (("instance_type", "cloud_type"),)


def syntheticdatarequest_expires_at_default():
    """
    Get default value for SyntheticDataRequest.expires_at.

    We always want synthetic data to expire within one day. If someone has not
    already explicitly deleted it by then, a periodic process will delete it soon.
    """
    return get_now() + timedelta(days=1)


class SyntheticDataRequest(BaseModel):
    """
    Synthetic data request definition which may be used for "live" test operations.

    All other objects referenced by a SyntheticDataRequest object should be treated as
    volatile, temporary data that may be destroyed soon after their creation.
    """

    # Requested inputs that can *only* be set at creation:
    cloud_type = models.CharField(
        max_length=32,
        choices=((AWS_PROVIDER_STRING, "AWS"), (AZURE_PROVIDER_STRING, "Azure")),
    )
    since_days_ago = models.PositiveIntegerField(default=7)
    account_count = models.PositiveIntegerField(default=1)
    image_count = models.PositiveIntegerField(default=10)
    image_ocp_chance = models.FloatField(
        default=0.5,
        validators=[validators.MinValueValidator(0), validators.MaxValueValidator(1)],
    )
    image_rhel_chance = models.FloatField(
        default=0.5,
        validators=[validators.MinValueValidator(0), validators.MaxValueValidator(1)],
    )
    image_other_owner_chance = models.FloatField(
        default=0.5,
        validators=[validators.MinValueValidator(0), validators.MaxValueValidator(1)],
    )
    instance_count = models.PositiveIntegerField(default=100)
    run_count_per_instance_min = models.IntegerField(
        default=1, validators=[validators.MinValueValidator(0)]
    )
    run_count_per_instance_mean = models.FloatField(
        default=1.0, validators=[validators.MinValueValidator(0)]
    )
    hours_per_run_min = models.FloatField(
        default=1.0, validators=[validators.MinValueValidator(0)]
    )
    hours_per_run_mean = models.FloatField(
        default=2.0, validators=[validators.MinValueValidator(0)]
    )
    hours_between_runs_mean = models.FloatField(
        default=8.0, validators=[validators.MinValueValidator(0)]
    )

    expires_at = models.DateTimeField(default=syntheticdatarequest_expires_at_default)

    # References to objects that may be synthesized after initial creation:
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, db_index=True, null=True
    )
    machine_images = models.ManyToManyField(MachineImage)

    def is_ready(self):
        """Determine if the synthetic data is ready to use."""
        if not self.user:
            return False
        start_date = self.user.date_joined.date()
        created_date = self.created_at.date()
        days_active = (created_date - start_date).days + 1
        concurrent_usages_count = ConcurrentUsage.objects.filter(
            user=self.user, date__gte=start_date, date__lte=created_date
        ).count()
        return concurrent_usages_count == days_active

    def __str__(self):
        """Get the string representation."""
        return repr(self)

    def __repr__(self):
        """Get an unambiguous string representation."""
        expires_at = (
            repr(self.expires_at.isoformat()) if self.expires_at is not None else None
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
            f"expires_at={expires_at}, "
            f"user_id={self.user_id}, "
            f"cloud_type={self.cloud_type}, "
            f"since_days_ago={self.since_days_ago}, "
            f"account_count={self.account_count}, "
            f"image_count={self.image_count}, "
            f"image_ocp_chance={self.image_ocp_chance}, "
            f"image_rhel_chance={self.image_rhel_chance}, "
            f"image_other_owner_chance={self.image_other_owner_chance}, "
            f"instance_count={self.instance_count}, "
            f"run_count_per_instance_min={self.run_count_per_instance_min}, "
            f"run_count_per_instance_mean={self.run_count_per_instance_mean}, "
            f"hours_per_run_min={self.hours_per_run_min}, "
            f"hours_per_run_mean={self.hours_per_run_mean}, "
            f"hours_between_runs_mean={self.hours_between_runs_mean}, "
            f"created_at={created_at}, "
            f"updated_at={updated_at}"
            f")"
        )
