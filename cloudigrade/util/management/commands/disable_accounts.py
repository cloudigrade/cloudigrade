"""Disable all currently-enabled CloudAccount objects."""
import logging

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from api import models

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Disables all currently-enabled CloudAccount objects."""

    def confirm(self, accounts_count):
        """Seek manual confirmation before proceeding."""
        question = (
            "This will DISABLE all enabled {} CloudAccount objects. "
            "Are you SURE you want to proceed?"
        ).format(accounts_count)
        result = input("{} [Y/n] ".format(question))
        if result.lower() != "y":
            self.stdout.write("Aborting.")
            return False
        return True

    def add_arguments(self, parser):
        """Add a command-line argument to skip confirmation prompt."""
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="automatically confirm destructive operation",
        )

    def disable_cloud_account(self, account):
        """Attempt to disable the CloudAccount gracefully."""
        try:
            account.disable(power_off_instances=False)
            return True
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Error when disabling {account} likely due to sources-api problem. "
                f"Will retry without sources-api integration. {e}",
                exc_info=True,
            )
        except Exception as e:
            logger.error(f"Error when disabling {account}. {e}", exc_info=True)
            return False

        try:
            # Note: The following account.refresh_from_db() is necessary because the
            # previous account.disable() failed to commit its transaction but likely
            # succeeded in updating its local representation of is_enabled=False.
            account.refresh_from_db()
            account.disable(power_off_instances=False, notify_sources=False)
            return True
        except Exception as e:
            logger.error(f"Error when deleting {account}. {e}", exc_info=True)
            return False

    def handle(self, *args, **options):
        """Handle the command execution."""
        if settings.IS_PRODUCTION:
            self.stdout.write(
                "You cannot run this command in production.", self.style.WARNING
            )
            return

        accounts = models.CloudAccount.objects.filter(is_enabled=True)
        accounts_count = accounts.count()
        if accounts_count == 0:
            self.stdout.write(
                "No enabled CloudAccount objects exist.", self.style.WARNING
            )
            return
        else:
            self.stdout.write(
                "Found {} CloudAccount objects to disable.".format(accounts_count)
            )
            if not options.get("confirm") and not self.confirm(accounts_count):
                return

            successes = 0
            for account in accounts:
                if self.disable_cloud_account(account):
                    successes += 1
            self.stdout.write(
                "Successfully disabled {} accounts.".format(successes),
                self.style.SUCCESS,
            )
