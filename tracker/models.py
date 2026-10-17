"""
MSP Tracker — Core Models
Location: tracker/models.py
"""

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import timedelta


# ===========================================================================
# MANAGED SERVICE PROVIDER
# ===========================================================================
class MSP(models.Model):
    """Managed Service Provider — NUKAP, MAXTECH, etc."""
    name = models.CharField(max_length=100, unique=True)
    contact_person = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'MSP'
        verbose_name_plural = 'MSPs'
        ordering = ['name']

    def __str__(self):
        return self.name


# ===========================================================================
# SITE
# ===========================================================================
class Site(models.Model):
    """Master record for every tower/site."""

    SITE_TYPE_CHOICES = [
        ('GRID', 'Grid'),
        ('GRID_GENSET', 'Grid & Genset'),
        ('SOLAR', 'Solar'),
        ('SOLAR_GRID', 'Solar & Grid'),
        ('SOLAR_GENSET', 'Solar & Genset'),
        ('SOLAR_GRID_GENSET', 'Solar & Grid & Genset'),
    ]

    site_id = models.CharField(max_length=50, unique=True, db_index=True)
    site_name = models.CharField(max_length=200)
    town = models.CharField(max_length=100, blank=True)
    province = models.CharField(max_length=100, db_index=True)
    site_type = models.CharField(
        max_length=30, choices=SITE_TYPE_CHOICES, default='GRID'
    )
    mno_list = models.CharField(
        max_length=500, blank=True,
        help_text="Comma-separated MNOs present at site"
    )
    msp = models.ForeignKey(
        MSP, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sites'
    )

    # Location
    longitude = models.FloatField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)

    # Status
    is_active = models.BooleanField(default=True)
    is_off_air = models.BooleanField(default=False)

    # Auto-derived flags (set in save())
    has_dg = models.BooleanField(default=False, editable=False)
    has_solar = models.BooleanField(default=False, editable=False)
    has_grid = models.BooleanField(default=False, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['site_id']
        indexes = [
            models.Index(fields=['province', 'site_id']),
            models.Index(fields=['has_dg']),
            models.Index(fields=['is_active']),
        ]

    def save(self, *args, **kwargs):
        st = self.site_type or ''
        self.has_dg = 'GENSET' in st
        self.has_solar = 'SOLAR' in st
        self.has_grid = 'GRID' in st
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.site_id} — {self.site_name}"

    # ----------------------------------------------------------------
    # CORE BUSINESS LOGIC (the reason this platform exists)
    # ----------------------------------------------------------------
    @property
    def last_ppm_date(self):
        """Most recent PPM completion date."""
        rec = self.maintenance_records.filter(
            maintenance_type='PPM', status='DONE'
        ).order_by('-service_date').first()
        return rec.service_date if rec else None

    @property
    def last_dg_service_date(self):
        """Most recent DG service date."""
        rec = self.maintenance_records.filter(
            maintenance_type='DG_SERVICE', status='DONE'
        ).order_by('-service_date').first()
        return rec.service_date if rec else None

    @property
    def last_dg_run_hours(self):
        """Most recent DG run-hour reading."""
        rec = self.maintenance_records.filter(
            maintenance_type='DG_SERVICE',
            dg_run_hours__isnull=False,
        ).order_by('-service_date').first()
        return rec.dg_run_hours if rec else None

    @property
    def ppm_due_date(self):
        """Next PPM due date: 3 months (DG) or 2 months (non-DG)."""
        last = self.last_ppm_date
        if not last:
            return None
        interval_days = 90 if self.has_dg else 60
        return last + timedelta(days=interval_days)

    @property
    def dg_service_due_date(self):
        """Next DG service due date: 3 months after last."""
        last = self.last_dg_service_date
        if not last:
            return None
        return last + timedelta(days=90)

    @property
    def is_ppm_overdue(self):
        """True if PPM is overdue."""
        due = self.ppm_due_date
        if due is None:
            return True  # Never serviced
        return timezone.now().date() > due

    @property
    def is_dg_service_overdue(self):
        """DG is overdue if >3 months OR >25,000 run hours."""
        if not self.has_dg:
            return False
        due = self.dg_service_due_date
        run_hours = self.last_dg_run_hours
        date_overdue = (due is None) or (timezone.now().date() > due)
        hours_overdue = run_hours is not None and float(run_hours) >= 25000
        return date_overdue or hours_overdue

    @property
    def overdue_reasons(self):
        """Human-readable list explaining why this site is flagged."""
        reasons = []
        if self.is_ppm_overdue:
            due = self.ppm_due_date
            if due is None:
                reasons.append("Never serviced")
            else:
                days = (timezone.now().date() - due).days
                reasons.append(f"PPM overdue by {days} days")
        if self.is_dg_service_overdue:
            run_hours = self.last_dg_run_hours
            if run_hours and float(run_hours) >= 25000:
                reasons.append(f"DG at {run_hours} hrs (>25,000)")
            else:
                reasons.append("DG service overdue")
        return reasons

    @property
    def status_color(self):
        """'red' / 'yellow' / 'green' for dashboards."""
        if self.is_ppm_overdue or self.is_dg_service_overdue:
            return 'red'
        due = self.ppm_due_date
        if due and (due - timezone.now().date()).days <= 14:
            return 'yellow'
        return 'green'


# ===========================================================================
# MAINTENANCE RECORD
# ===========================================================================
class MaintenanceRecord(models.Model):
    """Every maintenance activity ever logged."""

    MAINTENANCE_TYPE_CHOICES = [
        ('PPM', 'Preventive Maintenance'),
        ('DG_SERVICE', 'DG Service'),
        ('SOLAR_CLEANING', 'Solar Cleaning'),
        ('AIRCON_SERVICE', 'Aircon Service'),
        ('CORRECTIVE', 'Corrective Maintenance'),
    ]

    STATUS_CHOICES = [
        ('DONE', 'Done'),
        ('NO_ACCESS', 'No Access'),
        ('PENDING', 'Pending'),
        ('FAILED', 'Failed'),
    ]

    site = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name='maintenance_records'
    )
    maintenance_type = models.CharField(
        max_length=30, choices=MAINTENANCE_TYPE_CHOICES, db_index=True
    )
    service_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='DONE'
    )
    ref_number = models.CharField(max_length=100, blank=True)
    technician_name = models.CharField(max_length=200, blank=True)

    # DG specific
    dg_run_hours = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    dg_make = models.CharField(max_length=50, blank=True)

    # Electrical readings
    load_current = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    earth_resistance = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )

    comment = models.TextField(blank=True)
    source_file = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-service_date']
        indexes = [
            models.Index(fields=['site', 'maintenance_type', '-service_date']),
        ]

    def __str__(self):
        return f"{self.site.site_id} — {self.get_maintenance_type_display()} on {self.service_date}"


# ===========================================================================
# REFUELING PLAN
# ===========================================================================
class RefuelingPlan(models.Model):
    """Monthly refuelling plan per site."""
    site = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name='refueling_plans'
    )
    plan_month = models.DateField(help_text="First day of the month")
    planned_fuel_litres = models.DecimalField(max_digits=10, decimal_places=2)
    dg_status = models.CharField(max_length=50, blank=True)
    dg_make = models.CharField(max_length=50, blank=True)
    engine_capacity_kva = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    tank_capacity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = ('site', 'plan_month')
        ordering = ['-plan_month', 'site__site_id']

    def __str__(self):
        return f"{self.site.site_id} — {self.plan_month:%b %Y} — {self.planned_fuel_litres}L"

# ===========================================================================
# REFUELING ACTUAL
# ===========================================================================
class RefuelingActual(models.Model):
    """Actual fuel issued per site per month (from fuel receipts / mobile DG logs)."""
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='refueling_actuals')
    actual_month = models.DateField()
    actual_litres = models.DecimalField(max_digits=10, decimal_places=2)
    fuel_receipt_number = models.CharField(max_length=100, blank=True)
    entered_by = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('site', 'actual_month')
        ordering = ['-actual_month']

    @property
    def variance_litres(self):
        """Difference between planned and actual"""
        plan = self.site.refueling_plans.filter(plan_month=self.actual_month).first()
        if not plan:
            return None
        return self.actual_litres - plan.planned_fuel_litres

    @property
    def variance_pct(self):
        """% variance from plan"""
        plan = self.site.refueling_plans.filter(plan_month=self.actual_month).first()
        if not plan or plan.planned_fuel_litres == 0:
            return None
        return float(self.variance_litres / plan.planned_fuel_litres * 100)

    @property
    def is_anomaly(self):
        """Flag if >25% over or under plan"""
        v = self.variance_pct
        return v is not None and abs(v) > 25

# ===========================================================================
# ENERGY PURCHASE (ZESCO tokens)
# ===========================================================================
class EnergyPurchase(models.Model):
    """Grid power purchases."""
    site = models.ForeignKey(
        Site, on_delete=models.CASCADE, related_name='energy_purchases'
    )
    meter_number = models.CharField(max_length=50, blank=True)
    purchase_date = models.DateField()
    amount_zmw = models.DecimalField(max_digits=12, decimal_places=2)
    units_kwh = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    verification_status = models.CharField(max_length=100, blank=True)
    field_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-purchase_date']

    def __str__(self):
        return f"{self.site.site_id} — {self.amount_zmw} ZMW on {self.purchase_date}"


# ===========================================================================
# USER PROFILE (extends Django's User with role + MSP link)
# ===========================================================================
class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('ADMIN', 'System Admin'),
        ('MANAGER', 'Regional Manager'),
        ('MSP', 'MSP User'),
        ('TECH', 'Technician'),
    ]

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ADMIN')
    msp = models.ForeignKey(
        MSP, on_delete=models.SET_NULL, null=True, blank=True,
        help_text="Only for MSP role"
    )
    province = models.CharField(
        max_length=100, blank=True,
        help_text="Only for Manager role"
    )

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)



# ===========================================================================
# UPLOAD LOG (audit trail for imports)
# ===========================================================================
class UploadLog(models.Model):
    """Records every Excel file upload."""
    filename = models.CharField(max_length=300)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    rows_imported = models.IntegerField(default=0)
    rows_failed = models.IntegerField(default=0)
    status = models.CharField(max_length=20, default='SUCCESS')
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.filename} ({self.uploaded_at:%Y-%m-%d})"

