"""Management command for producing an hourly usage report."""
import dateutil.tz as tz
import dateutil.parser as parser
import json

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from account import reports


class Command(BaseCommand):
    """Command to produce an hourly report from the command line.

    Example usage:

        START_TIME='2018-02-01T00:00:00'
        END_TIME='2018-03-01T00:00:00'
        ACCOUNT_ID=518028203513
        python manage.py report_usage ${START_TIME} ${END_TIME} ${ACCOUNT_ID}
    """

    help = _('Produces report of hourly RHEL usage.')

    def add_arguments(self, argparser):
        """Add arguments for start and end times and list of account IDs."""
        argparser.add_argument('start',
                               help=_('Start time for reporting (inclusive)'))
        argparser.add_argument('end',
                               help=_('End time for reporting (exclusive)'))
        argparser.add_argument('account_id', nargs='+', type=int,
                               help=_('One or more AWS account IDs to report'))

    def handle(self, *args, **options):
        """Get a report for the given arguments and print JSON to stdout."""
        start = parser.parse(options['start'])
        end = parser.parse(options['end'])
        account_ids = options['account_id']

        # Default to UTC if not included.
        if not start.tzinfo:
            start = start.replace(tzinfo=tz.tzutc())
        if not end.tzinfo:
            end = end.replace(tzinfo=tz.tzutc())

        results = {
            account_id: reports.get_hourly_usage(start, end, account_id)
            for account_id in account_ids
        }

        self.stdout.write(json.dumps(results))
