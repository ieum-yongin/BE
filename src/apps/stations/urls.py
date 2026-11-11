from django.urls import path

from .views import station_detail, station_list, station_map, station_usage

urlpatterns = [
    path("map/", station_map, name="station-map"),
    path("", station_list, name="station-list"),
    path("<str:station_id>/usage/", station_usage, name="station-usage"),
    path("<str:station_id>/", station_detail, name="station-detail"),
]
