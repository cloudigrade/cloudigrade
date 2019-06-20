"""Cloudigrade Base Models."""
import logging

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext as _
from polymorphic.models import PolymorphicModel

logger = logging.getLogger(__name__)


class BasePolymorphicModel(PolymorphicModel):
    """Abstract model to add automatic created_at and updated_at fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ('created_at',)


class BaseModel(models.Model):
    """Abstract model to add automatic created_at and updated_at fields."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ('created_at',)


class BaseGenericModel(BaseModel):
    """Abstract model to add fields needed for Generic Relationships."""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    class Meta:
        abstract = True
        ordering = ('created_at',)

    @transaction.atomic
    def delete(self, **kwargs):
        """Delete the platform specific model along with the generic model."""
        logger.info(
            _(
                'deleting %(self_class)s-related content object: '
                '%(content_object)s'
            ),
            {
                'self_class': self.__class__.__name__,
                'content_object': self.content_object,
            },
        )
        self.content_object.delete()
        logger.info(_('deleting %s'), self)
        super().delete(**kwargs)
