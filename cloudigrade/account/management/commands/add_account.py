from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'This adds aws accounts'

    def handle(self, *args, **options):
        # FIXME: Implement this
        self.stdout.write(self.style.SUCCESS('STUB RESPONSE'))
