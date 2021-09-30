"""Manage PSKs for micro-services."""
import binascii
import os

from django.core.management import BaseCommand
from django.utils.translation import gettext as _


class Command(BaseCommand):
    """Manage PSKs for micro-services."""

    help = _(
        "Manages PSKs for micro-services."
        " This command allows us to create a random 32 hex digit PSK"
        " for a new micro-service. Once the new PSK is appended to the"
        " cloudigrade-psks in the cloudigrade-app-secret as"
        " micro-service-name:psk, the micro service can access the"
        " Cloudigrade API with the new x-rh-cloudigrade-psk header."
    )

    def add_arguments(self, parser):
        """Adding command-line arguments to the psk command."""
        parser.add_argument(
            "-c",
            "--create",
            action="store_true",
            help=_("Create a new PSK"),
        )

    def create_psk(self):
        """
        Create a random 32 hex digit PSK for a new micro-service.

        PSKs are dash seperated as in the following example:

                302df7dd-7e9d9b2c-3d0ac1cd-92414092
        """
        print(binascii.b2a_hex(os.urandom(16), "-", 4).decode())

    def handle(self, *args, **options):
        """Handle the DJANGO psk command execution."""
        if options.get("create"):
            self.create_psk()
