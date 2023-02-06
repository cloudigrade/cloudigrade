"""Cloudigrade API v2 Models."""
import logging
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models, transaction
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils.timezone import now
from django.utils.translation import gettext as _

from util.misc import get_now
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
            f"created_at=parse({created_at}), "
            f"updated_at=parse({updated_at})"
            f")"
        )

    def enable(self, disable_upon_failure=True):
        """
        Mark this CloudAccount as enabled and perform operations to make it so.

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

        if enabled_successfully:
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
        if notify_sources:
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
