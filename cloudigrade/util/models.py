"""Cloudigrade Base Models."""
from django.db import models
from polymorphic.models import PolymorphicModel


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
