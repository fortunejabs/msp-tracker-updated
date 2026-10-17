from django.core.management.base import BaseCommand
from tracker.services.alerts import send_daily_digest


class Command(BaseCommand):
    help = 'Send daily overdue maintenance alerts'

    def handle(self, *args, **options):
        # In production, store recipient list in a model or env var
        recipients = ['ops@example.com']
        send_daily_digest(recipients)
        self.stdout.write(self.style.SUCCESS(f'Alert sent to {recipients}'))