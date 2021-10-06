"""Creates PSKs for micro-services."""
from django.core.management import BaseCommand
from django.utils.translation import gettext as _

from util.redhatcloud.psk import add_service_psk
from util.redhatcloud.psk import generate_psk
from util.redhatcloud.psk import normalize_service_name


class Command(BaseCommand):
    """Create PSKs for micro-services."""

    help = _(
        "Command to create a Cloudigrade PSK for micro-services."
        " This command allows us to create a random 32 hex digit PSK"
        " for a micro-service. Once the new PSK is appended to the"
        " cloudigrade-psks in the cloudigrade-app-secret as"
        " micro-service-name:psk, the micro service can access the"
        " Cloudigrade API with the new x-rh-cloudigrade-psk header."
    )

    def add_arguments(self, parser):
        """Adding command-line arguments to the psk command."""
        parser.add_argument(
            "--psks",
            type=str,
            default="",
            help=_("Current list of Cloudigrade PSKs"),
        )
        parser.add_argument(
            "svc_name",
            type=str,
            help=_("Service name for the new PSK"),
        )

        """Create a random PSK for a new micro-service."""

    def create_psk(self, options):
        """Given the current list of PSKs, create and add a new PSK."""
        psks = options["psks"]
        svc_name = normalize_service_name(options["svc_name"])
        new_psk = generate_psk()
        self.stdout.write(
            _(
                "\nService Name:             {}"
                "\nNew Cloudigrade PSK:      {}"
                "\nCurrent Cloudigrade PSKs: {}"
                "\nUpdated Cloudigrade PSKs: {}"
            ).format(svc_name, new_psk, psks, add_service_psk(psks, svc_name, new_psk))
        )

    def handle(self, *args, **options):
        """Handle the DJANGO create_psk command execution."""
        self.create_psk(options)
