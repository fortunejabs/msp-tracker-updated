# tracker/management/commands/import_excel.py

from django.core.management.base import BaseCommand
from datetime import date
from tracker.services.excel_importer import (
    import_site_master, import_ppm_report, import_dg_service, import_refueling_plan
)


class Command(BaseCommand):
    help = 'Import MSP Excel files'

    def add_arguments(self, parser):
        parser.add_argument('--type', required=True,
                            choices=['site_master', 'ppm', 'dg', 'refuel'])
        parser.add_argument('--file', required=True)
        parser.add_argument('--sheet', default='PPM LIST')
        parser.add_argument('--msp', default='NUKAP')
        parser.add_argument('--month', help='YYYY-MM-01 for refueling plans')

    def handle(self, *args, **options):
        t = options['type']
        f = options['file']

        if t == 'site_master':
            result = import_site_master(f, options['msp'])
        elif t == 'ppm':
            result = import_ppm_report(f, options['sheet'], options['msp'])
        elif t == 'dg':
            result = import_dg_service(f, options['msp'])
        elif t == 'refuel':
            month = date.fromisoformat(options['month'])
            result = import_refueling_plan(f, month, options['msp'])

        self.stdout.write(self.style.SUCCESS(f'Import complete: {result}'))