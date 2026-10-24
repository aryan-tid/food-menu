"""
URL configuration for core project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse

# Customize Django Admin Site Branding to match App Identity
admin.site.site_header = "Spice Garden Restaurant Admin"
admin.site.site_title = "Spice Garden Admin Portal"
admin.site.index_title = "Restaurant Operations & Data Management"

def favicon_view(request):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🍛</text></svg>'
    return HttpResponse(svg, content_type="image/svg+xml")

urlpatterns = [
    path('favicon.ico', favicon_view, name='favicon'),
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('menu.urls')),
    path('', include('orders.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
