"""Collection of tests for ``util.leaderrun.LeaderRun`` class."""
import datetime

import faker
from django.conf import settings
from django.test import TestCase

from util.leaderrun import LeaderRun

_faker = faker.Faker()


class LeaderRunTest(TestCase):
    """LeaderRun class test cases."""

    def test_default_ttl(self):
        """Assert that the ttl for running and completed are the defaults."""
        leader = LeaderRun(_faker.slug())
        self.assertEqual(leader.leader_running_ttl, settings.LEADER_RUNNING_TTL_DEFAULT)
        self.assertEqual(
            leader.leader_completed_ttl, settings.LEADER_COMPLETED_TTL_DEFAULT
        )

    def test_custom_ttl(self):
        """Assert that LeaderRun support custom ttl."""
        run_ttl = _faker.pyint()
        completed_ttl = _faker.pyint()
        leader = LeaderRun(
            _faker.slug(),
            leader_running_ttl=run_ttl,
            leader_completed_ttl=completed_ttl,
        )
        self.assertEqual(leader.leader_running_ttl, run_ttl)
        self.assertEqual(leader.leader_completed_ttl, completed_ttl)

    def test_set_as_running_succeeds(self):
        """Assert that set_as_running returns marks that feature is running."""
        leader = LeaderRun(_faker.slug())
        leader.set_as_running()
        self.assertTrue(leader.is_running())
        self.assertFalse(leader.has_completed())

    def test_is_running_false_for_non_started_features(self):
        """Assert that is_running is false for features that are not started."""
        leader = LeaderRun(_faker.slug())
        self.assertFalse(leader.is_running())

    def test_is_running_is_a_datetime(self):
        """Assert is_running gives us a datetime (e.g. time started)."""
        leader = LeaderRun(_faker.slug())
        leader.set_as_running()
        self.assertIsInstance(leader.is_running(), datetime.datetime)

    def test_set_as_completed_succeeds(self):
        """Assert that set_as_completed marks feature has completed."""
        leader = LeaderRun(_faker.slug())
        leader.set_as_completed()
        self.assertTrue(leader.has_completed())
        self.assertFalse(leader.is_running())

    def test_has_completed_false_for_non_started_features(self):
        """Assert that has_completed is false for features that have not started."""
        leader = LeaderRun(_faker.slug())
        self.assertFalse(leader.has_completed())

    def test_has_completed_is_a_datetime(self):
        """Assert has_completed gives us a datetime (e.g. time completed)."""
        leader = LeaderRun(_faker.slug())
        leader.set_as_completed()
        self.assertIsInstance(leader.has_completed(), datetime.datetime)

    def test_run(self):
        """Assert the leader.run completes successfully after a failure."""
        leader = LeaderRun(_faker.slug())
        with self.assertRaises(RuntimeError):
            with leader.run():
                raise RuntimeError("leader exception")
        self.assertTrue(leader.has_completed())
