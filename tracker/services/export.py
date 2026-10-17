import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from datetime import date
from io import BytesIO
from django.http import HttpResponse
from tracker.models import Site, MaintenanceRecord


HEADERS = [
    ('S/N', 6), ('Site ID', 14), ('Site Name', 34), ('Province', 14), ('Town', 14),
    ('MSP', 12), ('Site Type', 22), ('DG Make', 14), ('DG Status', 12),
    ('Last PPM Date', 14), ('PPM Due Date', 14), ('Overdue Days', 12),
    ('Last DG Service', 14), ('Last Run Hours', 12),
    ('Status', 10), ('Reasons', 40),
]


def _style_header(ws, row=1):
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for col, (name, width) in enumerate(HEADERS, start=1):
        c = ws.cell(row=row, column=col, value=name)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = width


def export_overdue_workbook(province=None, msp=None):
    """Generate an Excel workbook of all overdue sites."""
    wb = openpyxl.Workbook()

    # --- Sheet 1: DG Overdue ---
    ws1 = wb.active
    ws1.title = "DG Service Overdue"
    _style_header(ws1)

    dg_sites = [s for s in Site.objects.filter(is_active=True, has_dg=True,
                                               **({'province': province} if province else {}),
                                               **({'msp__name': msp} if msp else {}))
                if s.is_dg_service_overdue]

    for i, s in enumerate(dg_sites, start=1):
        last = s.last_dg_service_date
        overdue_days = (date.today() - s.dg_service_due_date).days if s.dg_service_due_date else ''
        ws1.append([
            i, s.site_id, s.site_name, s.province, s.town,
            s.msp.name if s.msp else '', s.get_site_type_display(),
            s.maintenance_records.filter(maintenance_type='DG_SERVICE').first().dg_make if s.maintenance_records.filter(maintenance_type='DG_SERVICE').exists() else '',
            'Runner',
            str(s.last_ppm_date or ''), str(s.ppm_due_date or ''),
            (date.today() - s.ppm_due_date).days if s.ppm_due_date and date.today() > s.ppm_due_date else 0,
            str(last or ''), s.last_dg_run_hours or '',
            s.status_color.upper(),
            '; '.join(s.overdue_reasons),
        ])

    # --- Sheet 2: PPM Overdue ---
    ws2 = wb.create_sheet("PPM Overdue")
    _style_header(ws2)

    ppm_sites = [s for s in Site.objects.filter(is_active=True,
                                                **({'province': province} if province else {}),
                                                **({'msp__name': msp} if msp else {}))
                 if s.is_ppm_overdue]

    for i, s in enumerate(ppm_sites, start=1):
        overdue_days = (date.today() - s.ppm_due_date).days if s.ppm_due_date else ''
        ws2.append([
            i, s.site_id, s.site_name, s.province, s.town,
            s.msp.name if s.msp else '', s.get_site_type_display(),
            '', 'Runner',
            str(s.last_ppm_date or ''), str(s.ppm_due_date or ''), overdue_days,
            str(s.last_dg_service_date or ''), s.last_dg_run_hours or '',
            s.status_color.upper(),
            '; '.join(s.overdue_reasons),
        ])

    # --- Sheet 3: Summary ---
    ws3 = wb.create_sheet("Summary")
    ws3.append(['Metric', 'Value'])
    ws3['A1'].font = Font(bold=True)
    ws3['B1'].font = Font(bold=True)
    ws3.append(['Total active sites', Site.objects.filter(is_active=True).count()])
    ws3.append(['Total DG sites', Site.objects.filter(is_active=True, has_dg=True).count()])
    ws3.append(['Total non-DG sites', Site.objects.filter(is_active=True, has_dg=False).count()])
    ws3.append(['DG service overdue', len(dg_sites)])
    ws3.append(['PPM overdue', len(ppm_sites)])
    ws3.append(['Report generated', str(date.today())])

    return wb


def download_overdue_excel(request):
    province = request.GET.get('province') or None
    msp = request.GET.get('msp') or None
    wb = export_overdue_workbook(province, msp)
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    resp = HttpResponse(
        buf.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = f'attachment; filename=overdue_report_{date.today()}.xlsx'
    return resp