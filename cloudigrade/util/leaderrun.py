"""Helper methods for helping track running/completed product features as leaders."""
import datetime
import time

from django.conf import settings
from django.core.cache import cache

LEADER_KEY_PREFIX = f"cloudigrade-{settings.CLOUDIGRADE_ENVIRONMENT}-leader-"


class LeaderRun(object):
    """Helper class for managing run/completed states of features as leaders."""

    def __init__(self, feature_key, **kwargs):
        """Initialize a LeaderRun object."""
        self.key = feature_key
        self.base_key = f"{LEADER_KEY_PREFIX}-{self.key}"
        self.running_key = f"{self.base_key}-running"
        self.completed_key = f"{self.base_key}-completed"
        self.leader_running_ttl = settings.LEADER_RUNNING_TTL_DEFAULT
        self.leader_completed_ttl = settings.LEADER_COMPLETED_TTL_DEFAULT
        for key, value in kwargs.items():
            setattr(self, key, value)

    def _now(self):
        """Return the current time for date stamping the keys."""
        return datetime.datetime.now()

    def set_as_running(self):
        """Set the feature as running."""
        cache.set(self.running_key, self._now(), timeout=self.leader_running_ttl)

    def is_running(self):
        """Return True if the feature is running."""
        return cache.get(self.running_key)

    def wait_for_completion(self):
        """Wait for the feature run to complete."""
        # In case of script errors and not a clean completion of the leader run,
        # this method will complete upon the normal expiration of the cached key.
        while cache.get(self.running_key):
            time.sleep(1)

    def set_as_completed(self):
        """Set the feature as done running and completed."""
        cache.set(self.running_key, None)
        return cache.set(
            self.completed_key, self._now(), timeout=self.leader_completed_ttl
        )

    def has_completed(self):
        """Return True if the feature has completed."""
        return cache.get(self.completed_key)
