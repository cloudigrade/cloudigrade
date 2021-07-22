"""Spawn a bunch of accounts, images, and powered-on instances."""
import collections
import datetime
import random
from argparse import ArgumentTypeError

from dateutil import tz
from dateutil.parser import parse as dateutil_parse
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.translation import gettext as _
from tqdm import tqdm

from api.models import InstanceEvent
from api.tasks import recalculate_concurrent_usage_for_user_id
from api.tests import helper as account_helper
from api.util import recalculate_runs_for_cloud_account_id
from util.misc import get_now
from util.tests import helper as util_helper


def float_non_negative(value):
    """Parse and assert that the value is a valid non-negative float."""
    float_value = float(value)
    if float_value < 0:
        raise ArgumentTypeError("%s is an invalid negative value" % value)
    return float_value


class Command(BaseCommand):
    """Spawn a bunch of accounts, images, and powered-on instances."""

    help = _(
        "Spawn a bunch of accounts, images, and powered-on instances. "
        'This command is intended only for generating "dummy" test data '
        "in non-production environments."
    )

    def add_arguments(self, parser):
        """Add command-line arguments."""
        parser.add_argument(
            "user_id", type=str, help=_("ID of the user who owns the accounts")
        )
        parser.add_argument(
            "since",
            type=dateutil_parse,
            help=_("earliest time instances may be started"),
        )
        parser.add_argument("--account_count", type=int, default=4)
        parser.add_argument("--image_count", type=int, default=100)
        parser.add_argument("--instance_count", type=int, default=5000)
        parser.add_argument("--cloud_type", type=str, default="aws")
        parser.add_argument(
            "--min_run_hours",
            type=float_non_negative,
            default=1.0,
            help=_("minimum hours an instance will run"),
        )
        parser.add_argument(
            "--mean_run_hours",
            type=float_non_negative,
            default=1.0,
            help=_("mean hours an instance will run"),
        )
        parser.add_argument(
            "--mean_run_count",
            type=float_non_negative,
            default=1.0,
            help=_("mean number of times an instance will run"),
        )
        parser.add_argument(
            "--mean_hours_between_runs",
            type=float_non_negative,
            default=8.0,
            help=_("mean hours between runs for the same instance"),
        )
        parser.add_argument(
            "--ocp_chance",
            type=float_non_negative,
            default=0.5,
            help=_("chance of new image finding OCP (0-1)"),
        )
        parser.add_argument(
            "--rhel_chance",
            type=float_non_negative,
            default=0.5,
            help=_("chance of new image finding RHEL (0-1)"),
        )
        parser.add_argument(
            "--other_owner_chance",
            type=float_non_negative,
            default=0.5,
            help=_(
                "chance of new image not belonging to one "
                "of this user's accounts (0-1)"
            ),
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="automatically confirm operation",
        )

    def confirm(self):
        """Seek manual confirmation before proceeding."""
        question = _("Are you SURE you want to proceed?")
        result = input("{} [Y/n] ".format(question))
        if result.lower() != "y":
            self.stdout.write("Aborting.")
            return False
        return True

    def create_accounts(self, user, options):
        """
        Create random CloudAccounts for the specified User.

        Returns:
            list[CloudAccount] accounts created

        """
        accounts = []
        for __ in tqdm(
            range(options["account_count"]),
            desc="Spawn account progress",
            unit="accounts",
        ):
            accounts.append(
                account_helper.generate_cloud_account(
                    user=user, cloud_type=options["cloud_type"]
                )
            )
        self.stdout.write(_("Created {} account(s)").format(len(accounts)))
        return accounts

    def create_images(self, accounts, options):
        """
        Create random MachineImages belonging (maybe) to the specified CloudAccounts.

        Returns:
            list[MachineImage] images created

        """
        images = []
        for __ in tqdm(
            range(options["image_count"]), desc="Spawn image progress", unit="images"
        ):
            images.append(
                account_helper.generate_image(
                    owner_aws_account_id=random.choice(accounts).cloud_account_id
                    if random.random() < options["other_owner_chance"]
                    else util_helper.generate_dummy_aws_account_id(),
                    rhel_detected=random.random() < options["rhel_chance"],
                    openshift_detected=random.random() < options["ocp_chance"],
                    cloud_type=options["cloud_type"],
                )
            )
        self.stdout.write(_("Created {} images").format(len(images)))
        return images

    def create_instances(self, accounts, images, options):
        """
        Create random Instances belonging to the specified CloudAccounts.

        Returns:
            list[Instance] instance created

        """
        instances = []
        for __ in tqdm(
            range(options["instance_count"]),
            desc="Spawn instance progress",
            unit="instances",
        ):
            instances.append(
                account_helper.generate_instance(
                    cloud_account=random.choice(accounts),
                    image=random.choice(images),
                    cloud_type=options["cloud_type"],
                )
            )
        self.stdout.write(_("Created {} instances(s)").format(len(instances)))
        return instances

    def create_events_for_instance(
        self,
        instance,
        since,
        now,
        seconds,
        max_run_count,
        max_secs_between_runs,
        min_run_secs,
        max_run_secs,
        runs_counts,
        cloud_type,
    ):
        """
        Create random InstanceEvents for a specific Instance.

        Returns:
            int number of events created

        """
        # Find an initial random time between the start and now.
        start_time = since + datetime.timedelta(seconds=random.randrange(0, seconds))
        runs_to_make = int(
            min(
                random.gauss(max_run_count / 2 + 0.5, max_run_count / 5),
                max_run_count,
            )
        )
        runs_made = 0
        events_count = 0
        for __ in range(runs_to_make):
            # Always create the first "on" event.
            account_helper.generate_single_instance_event(
                instance=instance,
                occurred_at=start_time,
                event_type=InstanceEvent.TYPE.power_on,
                cloud_type=cloud_type,
            )
            events_count += 1
            runs_made += 1

            run_duration = random.uniform(min_run_secs, max_run_secs)
            stop_time = start_time + datetime.timedelta(seconds=run_duration)

            if stop_time > now:
                # Don't allow creating events in the future.
                break

            account_helper.generate_single_instance_event(
                instance=instance,
                occurred_at=stop_time,
                event_type=InstanceEvent.TYPE.power_off,
                cloud_type=cloud_type,
            )
            events_count += 1

            # Find a new starting time for the next run.
            delay = random.randrange(0, max_secs_between_runs) + 1
            start_time = stop_time + datetime.timedelta(seconds=delay)
            if start_time > now:
                # Don't allow creating events in the future.
                break

        runs_counts[runs_made] += 1
        return events_count

    def create_events(self, instances, options):
        """
        Create random events for the list of Instances.

        Args:
            instances (list): instances for which to create events
            options (dict): command options

        Returns:
            tuple[int, dict] of events_count, runs_counts

        """
        since = options["since"]
        if not since.tzinfo:
            since = since.replace(tzinfo=tz.tzutc())
        now = get_now()
        seconds = int(datetime.timedelta.total_seconds(now - since))

        # Force reasonable not-negative defaults and convert to integer seconds.
        min_run_secs = int(options["min_run_hours"] * 3600)
        mean_run_secs = max(min_run_secs, int(options["mean_run_hours"] * 3600))
        max_run_secs = mean_run_secs * 2 - min_run_secs
        max_run_count = options["mean_run_count"] * 2
        max_secs_between_runs = int(options["mean_hours_between_runs"] * 3600 * 2)

        events_count = 0
        runs_counts = collections.defaultdict(int)
        if max_run_count and max_run_secs:
            for instance in tqdm(
                instances, desc="Spawn instance event progress", unit="events"
            ):
                events_count += self.create_events_for_instance(
                    instance,
                    since,
                    now,
                    seconds,
                    max_run_count,
                    max_secs_between_runs,
                    min_run_secs,
                    max_run_secs,
                    runs_counts,
                    options["cloud_type"],
                )
        return events_count, runs_counts

    @transaction.atomic()
    def handle(self, *args, **options):
        """Handle the command execution."""
        self.stdout.write(
            _(
                "This command will generate data representing:\n"
                "- {account_count} {cloud_type} account(s)\n"
                "- {image_count} {cloud_type} image(s)\n"
                "- {instance_count} {cloud_type} instance(s)\n"
                "- {mean_run_count} mean runs for each instance\n"
                "- {min_run_hours} minimum and {mean_run_hours} mean hours duration "
                "for each run\n"
                "- {mean_hours_between_runs} mean hours between runs for the same "
                "instance\n"
                "- power-on event(s) since {since}"
            ).format(**options)
        )

        if not options.get("confirm") and not self.confirm():
            return False

        user = User.objects.get(pk=options["user_id"])

        accounts = self.create_accounts(user, options)
        images = self.create_images(accounts, options)
        instances = self.create_instances(accounts, images, options)
        events_count, runs_counts = self.create_events(instances, options)

        self.stdout.write(_("Created {} instance(s)").format(len(instances)))
        self.stdout.write(_("Created {} events(s)").format(events_count))
        for key in sorted(dict(runs_counts).keys()):
            self.stdout.write(
                _("- {0} instance(s) will have {1} runs").format(runs_counts[key], key)
            )
        expected_runs_total = sum(
            (key * value for key, value in dict(runs_counts).items())
        )
        self.stdout.write(
            _("Expect {} new run(s) to be generated").format(expected_runs_total)
        )
        since = options["since"].replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=tz.tzutc()
        )
        for account in accounts:
            recalculate_runs_for_cloud_account_id(account.id, since)

        recalculate_concurrent_usage_for_user_id(user.id, since.date())
