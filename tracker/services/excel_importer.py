# tracker/services/excel_importer.py

import pandas as pd
from datetime import datetime
from decimal import Decimal, InvalidOperation
from django.db import transaction
from tracker.models import Site, MSP, MaintenanceRecord, RefuelingPlan


def _to_decimal(value):
    """Safely convert to Decimal or None"""
    if pd.isna(value) or value in ('', 'N/A', 'FC', 'DONE', None):
        return None
    try:
        return Decimal(str(value).replace(',', ''))
    except (InvalidOperation, ValueError):
        return None


def _to_date(value):
    """Safely convert to date"""
    if pd.isna(value) or value in ('', None):
        return None
    if isinstance(value, datetime):
        return value.date()
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def _map_site_type(raw):
    """Map Excel site type to our choices"""
    if not raw:
        return 'GRID'
    s = str(raw).upper()
    if 'SOLAR' in s and 'GENSET' in s and 'GRID' in s:
        return 'SOLAR_GRID_GENSET'
    if 'SOLAR' in s and 'GENSET' in s:
        return 'SOLAR_GENSET'
    if 'SOLAR' in s and 'GRID' in s:
        return 'SOLAR_GRID'
    if 'SOLAR' in s:
        return 'SOLAR'
    if 'GENSET' in s:
        return 'GRID_GENSET'
    return 'GRID'


# ============ SITE MASTER IMPORT ============

def import_site_master(file_path, msp_name='NUKAP'):
    """
    Import the Infratel site master file.
    Expects columns: Site ID, Site Name, Town, Province, Site type, MNOs
    """
    df = pd.read_excel(file_path)
    msp, _ = MSP.objects.get_or_create(name=msp_name)
    created, updated = 0, 0

    for _, row in df.iterrows():
        site_id = str(row.get('Site ID', '')).strip()
        if not site_id or site_id == 'nan':
            continue

        defaults = {
            'site_name': str(row.get('Site Name', '')).strip(),
            'town': str(row.get('Town', '')).strip(),
            'province': str(row.get('Province', '')).strip().upper(),
            'site_type': _map_site_type(row.get('Site type')),
            'mno_list': str(row.get('MNOs', '')).strip(),
            'msp': msp,
            'longitude': row.get('longitude') if not pd.isna(row.get('longitude')) else None,
            'latitude': row.get('latitude') if not pd.isna(row.get('latitude')) else None,
        }

        obj, was_created = Site.objects.update_or_create(
            site_id=site_id,
            defaults=defaults
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {'created': created, 'updated': updated}


# ============ PPM REPORT IMPORT ============

def import_ppm_report(file_path, sheet_name='PPM LIST', msp_name='NUKAP', source_label=''):
    """
    Import a PM report PPM LIST sheet.
    Flexible: uses column detection so it handles all your regional variants.
    """
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

    # Find header row — look for a row containing 'Site ID'
    header_row = None
    for i, row in df.iterrows():
        if row.astype(str).str.contains('Site ID', case=False, na=False).any():
            header_row = i
            break

    if header_row is None:
        return {'error': f'Could not find header row in sheet "{sheet_name}"'}

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)

    records_created = 0
    records_skipped = 0

    with transaction.atomic():
        for _, row in df.iterrows():
            site_id = str(row.get('Site ID', '')).strip()
            if not site_id or site_id in ('nan', 'None'):
                continue

            try:
                site = Site.objects.get(site_id=site_id)
            except Site.DoesNotExist:
                records_skipped += 1
                continue

            service_date = _to_date(row.get('Done Date') or row.get('DATE') or row.get('Service Date'))
            if not service_date:
                records_skipped += 1
                continue

            status_raw = str(row.get('Status', 'DONE')).strip().upper()
            status = 'DONE' if status_raw == 'DONE' else status_raw.replace(' ', '_')

            ref = str(row.get('REF NO') or row.get('REFERENCE NUMBER') or row.get('REF NUMBER') or '').strip()

            MaintenanceRecord.objects.create(
                site=site,
                maintenance_type='PPM',
                service_date=service_date,
                status=status,
                ref_number=ref,
                technician_name=str(row.get('SITE OWNER') or row.get('SITE OWNER/Technician') or row.get('SITE OWNER/technician') or '').strip(),
                load_current=_to_decimal(row.get('LOAD CURRENT')),
                earth_resistance=_to_decimal(row.get('EARTH RES (OMHS)') or row.get('EARTH TESTING')),
                comment=str(row.get('Comment', '')).strip(),
                source_file=source_label or file_path,
            )
            records_created += 1

    return {'created': records_created, 'skipped': records_skipped}


# ============ DG SERVICE IMPORT ============

def import_dg_service(file_path, msp_name='NUKAP', source_label=''):
    """
    Import a DG SERVICE sheet. Auto-detects region by scanning for headers.
    """
    xl = pd.ExcelFile(file_path)
    total_created = 0

    for sheet_name in xl.sheet_names:
        if 'DG' not in sheet_name.upper():
            continue

        df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

        header_row = None
        for i, row in df.iterrows():
            if row.astype(str).str.contains('Site ID|SITE ID', case=False, na=False).any():
                header_row = i
                break
        if header_row is None:
            continue

        df.columns = df.iloc[header_row]
        df = df.iloc[header_row + 1:].reset_index(drop=True)

        with transaction.atomic():
            for _, row in df.iterrows():
                site_id = str(row.get('Site ID') or row.get('SITE ID') or '').strip()
                if not site_id or site_id == 'nan':
                    continue
                try:
                    site = Site.objects.get(site_id=site_id)
                except Site.DoesNotExist:
                    continue

                service_date = _to_date(row.get('Service Date') or row.get('SERVICE DATE'))
                if not service_date:
                    continue

                MaintenanceRecord.objects.create(
                    site=site,
                    maintenance_type='DG_SERVICE',
                    service_date=service_date,
                    status='DONE',
                    ref_number=str(row.get('REF NUMBER') or row.get('REF NO') or '').strip(),
                    technician_name=str(row.get('SERVICED BY') or row.get('SITE OWNER') or '').strip(),
                    dg_run_hours=_to_decimal(row.get('RUNHOUR') or row.get('RUN HOUR')),
                    dg_type=str(row.get('DG MAKE') or row.get('DG  Type') or row.get('DG Type') or '').strip(),
                    comment=str(row.get('COMMENT', '')).strip(),
                    source_file=source_label or file_path,
                )
                total_created += 1

    return {'created': total_created}


# ============ REFUELING PLAN IMPORT ============

def import_refueling_plan(file_path, plan_month, msp_name='NUKAP'):
    """
    Import the monthly refuelling plan.
    plan_month should be a date object for the 1st of the month.
    """
    df = pd.read_excel(file_path, sheet_name=0, header=None)

    header_row = None
    for i, row in df.iterrows():
        if row.astype(str).str.contains('Site ID', case=False, na=False).any():
            header_row = i
            break
    if header_row is None:
        return {'error': 'Header not found'}

    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)

    created = 0
    with transaction.atomic():
        for _, row in df.iterrows():
            site_id = str(row.get('Site ID', '')).strip()
            if not site_id or site_id in ('nan', 'Mobile'):
                continue
            try:
                site = Site.objects.get(site_id=site_id)
            except Site.DoesNotExist:
                continue

            fuel = _to_decimal(row.get('Monthly refuelling plan-October 2026')
                               or row.get('Monthly refuelling plan-September 2026'))
            if fuel is None:
                continue

            RefuelingPlan.objects.update_or_create(
                site=site,
                plan_month=plan_month,
                defaults={
                    'planned_fuel_litres': fuel,
                    'dg_status': str(row.get('DG Status', '')).strip(),
                    'dg_make': str(row.get('DG Make', '')).strip(),
                    'engine_capacity_kva': _to_decimal(row.get('Engine Capacity (KVA)')),
                    'tank_capacity': _to_decimal(row.get('Tank Capacity')),
                    'comment': str(row.get('Other comment', '')).strip(),
                }
            )
            created += 1

    return {'created': created}