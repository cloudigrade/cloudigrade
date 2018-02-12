"""Cloudigrade Account Models."""
from django.db import models

from util.models import BaseModel


class Account(BaseModel):
    """Account model."""

    account_id = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        db_index=True
    )
    account_arn = models.CharField(max_length=256)
