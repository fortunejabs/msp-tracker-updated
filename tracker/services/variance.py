from datetime import date
from decimal import Decimal
from django.db.models import Sum
from tracker.models import Site, RefuelingPlan, RefuelingActual, EnergyPurchase
from calendar import monthrange


def months_between(start_date, end_date):
    """Yield first-of-month dates between start and end"""
    cur = start_date.replace(day=1)
    while cur <= end_date:
        yield cur
        if cur.month == 12:
            cur = cur.replace(year=cur.year + 1, month=1)
        else:
            cur = cur.replace(month=cur.month + 1)


def build_variance_report(year, month, province=None, msp=None):
    """
    Returns a list of dicts, one per site, for the given month:
    {
        'site': Site,
        'planned_litres': Decimal,
        'actual_litres': Decimal | None,
        'variance_litres': Decimal | None,
        'variance_pct': float | None,
        'grid_kwh': Decimal,  # from EnergyPurchase
        'status': 'OK' | 'OVER' | 'UNDER' | 'MISSING'
    }
    """
    plan_month = date(year, month, 1)
    sites = Site.objects.filter(is_active=True)
    if province:
        sites = sites.filter(province=province)
    if msp:
        sites = sites.filter(msp__name=msp)

    results = []
    for site in sites:
        plan = RefuelingPlan.objects.filter(site=site, plan_month=plan_month).first()
        actual = RefuelingActual.objects.filter(site=site, actual_month=plan_month).first()

        planned = plan.planned_fuel_litres if plan else None
        actual_l = actual.actual_litres if actual else None

        if planned is not None and actual_l is not None:
            variance = actual_l - planned
            pct = float(variance / planned * 100) if planned else 0
            if pct > 25:
                status = 'OVER'
            elif pct < -25:
                status = 'UNDER'
            else:
                status = 'OK'
        elif planned is not None:
            variance, pct, status = None, None, 'MISSING'
        else:
            continue  # Not a refuelled site this month

        # Grid consumption for that month
        grid_kwh = EnergyPurchase.objects.filter(
            site=site,
            purchase_date__year=year,
            purchase_date__month=month,
        ).aggregate(total=Sum('units_kwh'))['total'] or Decimal('0')

        results.append({
            'site': site,
            'planned_litres': planned,
            'actual_litres': actual_l,
            'variance_litres': variance,
            'variance_pct': pct,
            'grid_kwh': grid_kwh,
            'status': status,
        })

    return results