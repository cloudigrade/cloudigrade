"""DRF serializers for the cloudigrade internal API."""

from django_celery_beat.models import PeriodicTask
from rest_framework import serializers
from rest_framework.fields import CharField, ChoiceField, JSONField, ListField
from rest_framework.serializers import ModelSerializer, Serializer

from api import models
from api.clouds.aws import models as aws_models
from api.clouds.azure import models as azure_models
from api.models import User


class InternalUserSerializer(ModelSerializer):
    """Serialize User for the internal API."""

    # Include the account_number in the "username" field for backward compatability.
    username = CharField(source="account_number", read_only=True)

    class Meta:
        model = User
        fields = (
            "date_joined",
            "id",
            "uuid",
            "username",
            "account_number",
            "org_id",
            "is_permanent",
        )


class InternalUserTaskLockSerializer(ModelSerializer):
    """Serialize UserTaskLock for the internal API."""

    class Meta:
        model = models.UserTaskLock
        fields = "__all__"


class InternalCloudAccountSerializer(ModelSerializer):
    """Serialize CloudAccount for the internal API."""

    class Meta:
        model = models.CloudAccount
        fields = "__all__"


class InternalAwsCloudAccountSerializer(ModelSerializer):
    """Serialize AwsCloudAccount for the internal API."""

    class Meta:
        model = aws_models.AwsCloudAccount
        fields = "__all__"


class InternalAzureCloudAccountSerializer(ModelSerializer):
    """Serialize AzureCloudAccount for the internal API."""

    class Meta:
        model = azure_models.AzureCloudAccount
        fields = "__all__"


class InternalPeriodicTaskSerializer(ModelSerializer):
    """Serialize PeriodicTask for the internal API."""

    # Important note: last_run_at is redefined here because in the underlying model it
    # has "editable=False" which coerces DRF into making it a read-only field, but we
    # specifically want it writable from this serializer.
    last_run_at = serializers.DateTimeField()

    class Meta:
        model = PeriodicTask
        fields = "__all__"

        # For now, *all* of the fields *except* "last_run_at" are read-only.
        # We may relax this later as needed, but we want to minimize use of this API.
        # PeriodicTask objects should normally be updated by the beat's config directly
        # or by in-app model changes.
        read_only_fields = tuple(
            set(f.name for f in model._meta.get_fields()) - set(("last_run_at",))
        )


class InternalRedisRawInputSerializer(Serializer):
    """Serializer to validate input for the internal redis_raw API."""

    nondestructive_commands = [
        # server management commands
        "config_get",  # get the values of configuration parameters
        "dbsize",  # return the number of keys in the database
        "info",  # get information and statistics about the server
        "lolwut",  # display the redis version
        "memory_stats",  # show memory usage details
        "memory_usage",  # estimate the memory usage of a key
        "slowlog_get",  # get the slow log's entries
        # generic commands
        "exists",  # determine if a key exists
        "expiretime",  # get the expiration unix timestamp for a key
        "get",  # get the value of a key
        "keys",  # find all keys matching the given pattern
        "ttl",  # get the time to live for a key in seconds
        "type",  # get the type of a key
        # list commands
        "llen",  # get the length of a list
        "lrange",  # get a range of elements from a list
        # set commands
        "scard",  # get the number of members in a set
        "sismember",  # determine if a given value is a member of a set
        "smembers",  # list members of the set with the given key
    ]

    destructive_commands = [
        # generic commands
        "delete",  # delete a key
        "expire",  # set a key's time to live in seconds
        "mset",  # set multiple values to multiple keys
        "set",  # set the string value of a key
        # list commands
        "lmove",  # pop an element from a list, push it to another list, and return it
        "lmpop",  # pop elements from a list
        "lpop",  # remove and get the first elements from a list
        "lpush",  # prepend one or multiple elements to a list
        "rpop",  # remove and get the last elements from a list
        "rpush",  # append one or multiple elements to a list
    ]

    allowed_commands = nondestructive_commands + destructive_commands

    command = ChoiceField(allowed_commands, required=True)
    args = ListField(required=False, allow_empty=True, child=CharField(min_length=1))


class InternalRunTaskInputSerializer(Serializer):
    """Serializer to validate input for the internal run_task API."""

    task_name = CharField(required=True)
    kwargs = JSONField(required=False)
