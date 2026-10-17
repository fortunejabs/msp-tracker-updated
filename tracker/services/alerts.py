# tracker/services/alerts.py

from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
from tracker.models import Site


def generate_overdue_digest():
    """Returns a text digest of all overdue sites"""
    lines = [f"Overdue Maintenance Report - {timezone.now().date()}", "=" * 60]

    dg_overdue = [s for s in Site.objects.filter(is_active=True, has_dg=True) if s.is_dg_service_overdue]
    ppm_overdue = [s for s in Site.objects.filter(is_active=True) if s.is_ppm_overdue]

    lines.append(f"\nDG Service Overdue ({len(dg_overdue)}):")
    for s in dg_overdue:
        lines.append(f"  - {s.site_id} | {s.site_name} | Last: {s.last_dg_service_date} | Hours: {s.last_dg_run_hours}")

    lines.append(f"\nPPM Overdue ({len(ppm_overdue)}):")
    for s in ppm_overdue:
        lines.append(f"  - {s.site_id} | {s.site_name} | Last: {s.last_ppm_date}")

    return "\n".join(lines)


def send_daily_digest(recipients):
    body = generate_overdue_digest()
    send_mail(
        subject=f"[MSP Tracker] Daily Maintenance Alert - {timezone.now().date()}",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=recipients,
        fail_silently=False,
    )