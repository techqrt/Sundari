from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API Docs
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Auth & Users
    path('auth/', include('sunndari_apps.authentication.urls')),
    path('users/', include('sunndari_apps.users.urls')),

    # Lookup / Master Data
    path('core/', include('sunndari_apps.core.urls')),
    path('helper/', include('sunndari_apps.helper_apis.urls')),

    # Business Modules
    path('artists/', include('sunndari_apps.artists.urls')),
    path('customers/', include('sunndari_apps.customers.urls')),
    path('notifications/', include('sunndari_apps.notifications.urls')),
    path('chat/', include('sunndari_apps.chat.urls')),

    # Admin Panel
    path('admin-panel/', include('sunndari_apps.admin_panel.urls')),

    # Activity Log
    path('activity/', include('sunndari_apps.activity_log.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
