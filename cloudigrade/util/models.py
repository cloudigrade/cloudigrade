"""Cloudigrade Base Models."""
import logging

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class BaseModel(models.Model):
    """Abstract model to add automatic created_at and updated_at fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("created_at",)


class BaseGenericModel(BaseModel):
    """Abstract model to add fields needed for Generic Relationships."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    class Meta:
        abstract = True
        ordering = ("created_at",)


@receiver(post_delete)
def basegenericmodel_post_delete_callback(sender, instance, *args, **kwargs):
    """
    Delete the platform specific model along with the generic model.

    Note that this receiver catches all post_delete signals, but only
    acts if the sender is a subclass of BaseGenericModel.

    Note: Signal receivers must accept keyword arguments (**kwargs).
    """
    if issubclass(sender, BaseGenericModel):
        logger.info(
            _("deleting %(self_class)s-related content object: %(content_object)s"),
            {
                "self_class": sender.__class__.__name__,
                "content_object": instance.content_object,
            },
        )
        if instance.content_object is not None:
            instance.content_object.delete()
            logger.info(_("deleting %s"), instance)
