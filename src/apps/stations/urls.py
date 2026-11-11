from django.urls import path

from .views import station_list, station_map

urlpatterns = [
    path("map/", station_map, name="station-map"),
    path("", station_list, name="station-list"),
]
