"""
MSP Tracker — Django Admin configuration.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe

from .models import (
    MSP, Site, MaintenanceRecord, RefuelingPlan, EnergyPurchase,
    UserProfile, UploadLog,
)


# ===========================================================================
# USER PROFILE INLINE (extends the User admin)
# ===========================================================================
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    fk_name = 'user'
    verbose_name_plural = 'Profile (Role & MSP)'


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name',
                    'get_role', 'is_staff', 'is_active')

    def get_role(self, obj):
        try:
            return obj.profile.get_role_display()
        except UserProfile.DoesNotExist:
            return '—'
    get_role.short_description = 'Role'


# Re-register User with our custom admin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ===========================================================================
# MSP
# ===========================================================================
@admin.register(MSP)
class MSPAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact_person', 'email', 'phone', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'contact_person', 'email')


# ===========================================================================
# SITE
# ===========================================================================
@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = (
        'site_id_link', 'site_name', 'province', 'town', 'msp',
        'site_type', 'colored_status', 'last_ppm_date',
        'last_dg_service_date', 'last_dg_run_hours',
    )
    list_filter = (
        'province', 'msp', 'site_type', 'has_dg',
        'is_active', 'is_off_air',
    )
    search_fields = ('site_id', 'site_name', 'town')
    readonly_fields = (
        'has_dg', 'has_solar', 'has_grid',
        'created_at', 'updated_at',
        'computed_status_panel',
    )
    list_per_page = 50

    fieldsets = (
        ('Identity', {
            'fields': ('site_id', 'site_name', 'msp')
        }),
        ('Location', {
            'fields': ('province', 'town', 'longitude', 'latitude')
        }),
        ('Classification', {
            'fields': ('site_type', 'mno_list',
                       'has_dg', 'has_solar', 'has_grid')
        }),
        ('Status', {
            'fields': ('is_active', 'is_off_air')
        }),
        ('Computed Status (read-only)', {
            'fields': ('computed_status_panel',),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def site_id_link(self, obj):
        url = reverse('admin:tracker_site_change', args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj.site_id)
    site_id_link.short_description = 'Site ID'
    site_id_link.admin_order_field = 'site_id'

    def colored_status(self, obj):
        color_map = {
            'red': '#dc3545',
            'yellow': '#ffc107',
            'green': '#28a745',
        }
        color = color_map.get(obj.status_color, '#6c757d')
        return format_html(
            '<span style="background:{};color:white;padding:3px 10px;'
            'border-radius:3px;font-weight:bold;">{}</span>',
            color, obj.status_color.upper()
        )
    colored_status.short_description = 'Status'

    def computed_status_panel(self, obj):
        """Rich panel shown on the detail page."""
        if not obj or not obj.pk:
            return '—'

        html = ['<table style="width:100%;max-width:600px;">']

        def row(label, value, color='#333'):
            html.append(
                f'<tr><td style="padding:6px;font-weight:bold;">{label}</td>'
                f'<td style="padding:6px;color:{color};">{value}</td></tr>'
            )

        ppm_color = '#dc3545' if obj.is_ppm_overdue else '#28a745'
        dg_color = '#dc3545' if obj.is_dg_service_overdue else '#28a745'

        row('Last PPM', obj.last_ppm_date or 'Never')
        row('Next PPM due', obj.ppm_due_date or '—')
        row('PPM overdue?', 'YES' if obj.is_ppm_overdue else 'No', ppm_color)

        if obj.has_dg:
            row('Last DG service', obj.last_dg_service_date or 'Never')
            row('Next DG due', obj.dg_service_due_date or '—')
            row('Last run hours', obj.last_dg_run_hours or '—')
            row('DG overdue?', 'YES' if obj.is_dg_service_overdue else 'No', dg_color)

        if obj.overdue_reasons:
            row('Reasons', '<br>'.join(obj.overdue_reasons), '#dc3545')

        html.append('</table>')
        return mark_safe(''.join(html))
    computed_status_panel.short_description = 'Computed Status'


# ===========================================================================
# MAINTENANCE RECORD
# ===========================================================================
@admin.register(MaintenanceRecord)
class MaintenanceRecordAdmin(admin.ModelAdmin):
    list_display = (
        'site', 'maintenance_type', 'service_date', 'status',
        'technician_name', 'dg_run_hours', 'ref_number',
    )
    list_filter = (
        'maintenance_type', 'status',
        'site__province', 'site__msp',
        'service_date',
    )
    search_fields = (
        'site__site_id', 'site__site_name',
        'ref_number', 'technician_name',
    )
    date_hierarchy = 'service_date'
    autocomplete_fields = ['site']
    list_per_page = 100
    ordering = ('-service_date',)


# ===========================================================================
# REFUELING PLAN
# ===========================================================================
@admin.register(RefuelingPlan)
class RefuelingPlanAdmin(admin.ModelAdmin):
    list_display = (
        'site', 'plan_month', 'planned_fuel_litres',
        'dg_status', 'dg_make', 'engine_capacity_kva',
    )
    list_filter = ('plan_month', 'site__province', 'dg_status')
    search_fields = ('site__site_id', 'site__site_name')
    autocomplete_fields = ['site']
    date_hierarchy = 'plan_month'


# ===========================================================================
# ENERGY PURCHASE
# ===========================================================================
@admin.register(EnergyPurchase)
class EnergyPurchaseAdmin(admin.ModelAdmin):
    list_display = (
        'site', 'purchase_date', 'amount_zmw', 'units_kwh',
        'meter_number', 'verification_status',
    )
    list_filter = ('purchase_date', 'verification_status')
    search_fields = ('site__site_id', 'meter_number')
    autocomplete_fields = ['site']
    date_hierarchy = 'purchase_date'


# ===========================================================================
# UPLOAD LOG
# ===========================================================================
@admin.register(UploadLog)
class UploadLogAdmin(admin.ModelAdmin):
    list_display = (
        'filename', 'uploaded_at', 'uploaded_by',
        'rows_imported', 'rows_failed', 'status',
    )
    list_filter = ('status', 'uploaded_at')
    readonly_fields = (
        'filename', 'uploaded_at', 'uploaded_by',
        'rows_imported', 'rows_failed', 'status', 'error_message',
    )


# ===========================================================================
# ADMIN BRANDING
# ===========================================================================
admin.site.site_header = 'MSP Tracker Administration'
admin.site.site_title = 'MSP Tracker Admin'
admin.site.index_title = 'Operations Dashboard'


