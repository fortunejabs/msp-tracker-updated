"""
MSP Tracker — Main views.
"""

from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.utils import timezone
from django.http import HttpResponse, JsonResponse

from .models import (
    Site, MSP, MaintenanceRecord, RefuelingPlan,
    EnergyPurchase, UploadLog,
)
from .permissions import scope_sites


# ===========================================================================
# DASHBOARD
# ===========================================================================
@login_required
def dashboard(request):
    """Main landing page with KPIs and top overdue sites."""
    today = timezone.now().date()
    sites_qs = scope_sites(Site.objects.filter(is_active=True), request.user)

    # Compute sets
    all_sites = list(sites_qs)
    overdue_dg = [s for s in all_sites if s.has_dg and s.is_dg_service_overdue]
    overdue_ppm = [s for s in all_sites if s.is_ppm_overdue]
    overdue_non_dg = [s for s in overdue_ppm if not s.has_dg]
    due_soon = [
        s for s in all_sites
        if not s.is_ppm_overdue
        and s.ppm_due_date
        and (s.ppm_due_date - today).days <= 14
    ]

    total_sites = len(all_sites)
    total_dg = sum(1 for s in all_sites if s.has_dg)
    total_non_dg = total_sites - total_dg

    # By-province breakdown
    provinces = {}
    for s in all_sites:
        provinces.setdefault(s.province, {'total': 0, 'overdue': 0})
        provinces[s.province]['total'] += 1
        if s.is_ppm_overdue or s.is_dg_service_overdue:
            provinces[s.province]['overdue'] += 1

    province_stats = [
        {'province': p, **v}
        for p, v in sorted(provinces.items())
    ]

    context = {
        'total_sites': total_sites,
        'total_dg': total_dg,
        'total_non_dg': total_non_dg,
        'overdue_dg_count': len(overdue_dg),
        'overdue_ppm_count': len(overdue_ppm),
        'overdue_non_dg_count': len(overdue_non_dg),
        'due_soon_count': len(due_soon),
        'overdue_dg': overdue_dg[:15],
        'overdue_ppm': overdue_ppm[:15],
        'due_soon': due_soon[:15],
        'province_stats': province_stats,
        'today': today,
    }
    return render(request, 'tracker/dashboard.html', context)


# ===========================================================================
# SITE DETAIL
# ===========================================================================
@login_required
def site_detail(request, site_id):
    site = get_object_or_404(Site, site_id=site_id)
    records = site.maintenance_records.all()[:50]
    refueling = site.refueling_plans.all()[:12]
    energy = site.energy_purchases.all()[:20]

    context = {
        'site': site,
        'records': records,
        'refueling': refueling,
        'energy': energy,
    }
    return render(request, 'tracker/site_detail.html', context)


# ===========================================================================
# SITE LIST
# ===========================================================================
@login_required
def site_list(request):
    sites_qs = scope_sites(Site.objects.filter(is_active=True), request.user)

    # Filters
    province = request.GET.get('province', '')
    msp_name = request.GET.get('msp', '')
    search = request.GET.get('search', '')

    if province:
        sites_qs = sites_qs.filter(province=province)
    if msp_name:
        sites_qs = sites_qs.filter(msp__name=msp_name)
    if search:
        sites_qs = sites_qs.filter(
            Q(site_id__icontains=search) | Q(site_name__icontains=search)
        )

    sites = sites_qs.select_related('msp')[:500]

    context = {
        'sites': sites,
        'provinces': Site.objects.values_list('province', flat=True).distinct(),
        'msps': MSP.objects.filter(is_active=True),
        'province': province,
        'msp_name': msp_name,
        'search': search,
    }
    return render(request, 'tracker/site_list.html', context)


# ===========================================================================
# OVERDUE REPORT
# ===========================================================================
@login_required
def overdue_report(request):
    """Full filterable list of overdue sites."""
    province = request.GET.get('province', '')
    msp_name = request.GET.get('msp', '')
    flag_type = request.GET.get('type', 'all')  # all | dg | ppm

    sites_qs = scope_sites(Site.objects.filter(is_active=True), request.user)
    if province:
        sites_qs = sites_qs.filter(province=province)
    if msp_name:
        sites_qs = sites_qs.filter(msp__name=msp_name)

    overdue = []
    for s in sites_qs:
        include = False
        if flag_type in ('all', 'ppm') and s.is_ppm_overdue:
            include = True
        if flag_type in ('all', 'dg') and s.is_dg_service_overdue:
            include = True
        if include:
            overdue.append(s)

    context = {
        'overdue_sites': overdue,
        'province': province,
        'msp_name': msp_name,
        'flag_type': flag_type,
        'provinces': Site.objects.values_list('province', flat=True).distinct(),
        'msps': MSP.objects.filter(is_active=True),
    }
    return render(request, 'tracker/overdue_report.html', context)


# ===========================================================================
# UPLOAD PAGE
# ===========================================================================
@login_required
def upload_report(request):
    if request.method == 'POST':
        messages.info(request, 'Upload handler will be added in the next phase.')
        return redirect('upload_report')

    logs = UploadLog.objects.all()[:20]
    return render(request, 'tracker/upload.html', {'logs': logs})


# ===========================================================================
# API ENDPOINTS (lightweight JSON, used by dashboard live refresh)
# ===========================================================================
@login_required
def api_dashboard_summary(request):
    """Returns KPI summary as JSON."""
    sites_qs = scope_sites(Site.objects.filter(is_active=True), request.user)
    all_sites = list(sites_qs)

    return JsonResponse({
        'total_sites': len(all_sites),
        'total_dg': sum(1 for s in all_sites if s.has_dg),
        'overdue_dg': sum(1 for s in all_sites if s.is_dg_service_overdue),
        'overdue_ppm': sum(1 for s in all_sites if s.is_ppm_overdue),
        'generated_at': timezone.now().isoformat(),
    })

    import json


@login_required
def map_view(request):
    sites = Site.objects.filter(is_active=True, latitude__isnull=False, longitude__isnull=False)
    features = []
    for s in sites:
        features.append({
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [s.longitude, s.latitude]},
            'properties': {
                'site_id': s.site_id,
                'site_name': s.site_name,
                'province': s.province,
                'site_type': s.get_site_type_display(),
                'has_dg': s.has_dg,
                'color': s.status_color,
                'url': f'/site/{s.site_id}/',
                'last_ppm': str(s.last_ppm_date or 'Never'),
                'last_dg': str(s.last_dg_service_date or 'N/A'),
                'reasons': '; '.join(s.overdue_reasons),
            }
        })

    geojson = {'type': 'FeatureCollection', 'features': features}
    return render(request, 'tracker/map.html', {
        'geojson': json.dumps(geojson),
        'total': len(features),
    })

from .permissions import scope_sites


@login_required
def dashboard(request):
    today = timezone.now().date()
    sites_qs = scope_sites(Site.objects.filter(is_active=True), request.user)

    total_sites = sites_qs.count()
    total_dg = sites_qs.filter(has_dg=True).count()
    total_non_dg = sites_qs.filter(has_dg=False).count()

    overdue_dg = [s for s in sites_qs.filter(has_dg=True) if s.is_dg_service_overdue]
    overdue_ppm = [s for s in sites_qs if s.is_ppm_overdue]
    overdue_non_dg = [s for s in overdue_ppm if not s.has_dg]

    due_soon = [s for s in sites_qs if not s.is_ppm_overdue and s.ppm_due_date and (s.ppm_due_date - today).days <= 14]

    province_stats = []
    for prov in sites_qs.values_list('province', flat=True).distinct():
        ps = sites_qs.filter(province=prov)
        province_stats.append({
            'province': prov,
            'total': ps.count(),
            'overdue': sum(1 for s in ps if s.is_ppm_overdue or s.is_dg_service_overdue),
        })

    return render(request, 'tracker/dashboard.html', {
        'total_sites': total_sites, 'total_dg': total_dg, 'total_non_dg': total_non_dg,
        'overdue_dg_count': len(overdue_dg),
        'overdue_ppm_count': len(overdue_ppm),
        'overdue_non_dg_count': len(overdue_non_dg),
        'due_soon_count': len(due_soon),
        'province_stats': province_stats,
        'overdue_dg': overdue_dg[:20],
        'overdue_ppm': overdue_ppm[:20],
        'due_soon': due_soon[:20],
    })


#

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json


@login_required
def tech_home(request):
    """Mobile-friendly list of today's assigned sites"""
    # For now: show overdue sites in user's scope
    from .permissions import scope_sites
    sites = scope_sites(Site.objects.filter(is_active=True), request.user)
    overdue = [s for s in sites if s.is_ppm_overdue or s.is_dg_service_overdue][:50]
    return render(request, 'tracker/tech_home.html', {'sites': overdue})


@csrf_exempt
@login_required
def api_log_visit(request):
    """Receive a visit logged from the PWA (may arrive offline-synced)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    data = json.loads(request.body)
    try:
        site = Site.objects.get(site_id=data['site_id'])
    except Site.DoesNotExist:
        return JsonResponse({'error': 'Site not found'}, status=404)

    rec = MaintenanceRecord.objects.create(
        site=site,
        maintenance_type=data.get('maintenance_type', 'PPM'),
        service_date=data.get('service_date'),
        status=data.get('status', 'DONE'),
        technician_name=request.user.get_full_name() or request.user.username,
        dg_run_hours=data.get('dg_run_hours'),
        load_current=data.get('load_current'),
        earth_resistance=data.get('earth_resistance'),
        comment=data.get('comment', ''),
        source_file='PWA',
        ref_number=f'PWA-{timezone.now().strftime("%Y%m%d%H%M%S")}',
    )
    return JsonResponse({'ok': True, 'record_id': rec.id})