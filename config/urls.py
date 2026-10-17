"""
MSP Tracker — URL configuration.
"""

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static


from tracker import views
from tracker.services.export import download_overdue_excel


urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Auth
    path('login/', auth_views.LoginView.as_view(
        template_name='tracker/login.html'
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(
        next_page='/login/'
    ), name='logout'),

    # App
    path('', views.dashboard, name='dashboard'),
    path('sites/', views.site_list, name='site_list'),
    path('site/<str:site_id>/', views.site_detail, name='site_detail'),
    path('overdue/', views.overdue_report, name='overdue_report'),
    path('upload/', views.upload_report, name='upload_report'),
    path('variance/', views.variance_report, name='variance_report'),
    path('map/', views.map_view, name='map_view'),
    path('overdue/export/', download_overdue_excel, name='download_overdue_excel'),
    path('tech/', views.tech_home, name='tech_home'),
    path('api/tech/log-visit/', views.api_log_visit, name='api_log_visit'),

    # API
    path('api/summary/', views.api_dashboard_summary, name='api_summary'),
]


# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)