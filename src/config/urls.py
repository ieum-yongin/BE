from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/stations/', include('apps.stations.urls')),
    path('api/alerts/', include('apps.alerts.urls')),
    path('api/routes/', include('apps.routes.urls')),
    path('api/simulations/', include('apps.simulations.urls')),
]
