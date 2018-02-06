from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'This adds aws accounts'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('AWS Account Added... probably'))
