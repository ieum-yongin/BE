from django.urls import path

from .views import simulation_create, simulation_detail, simulation_stops, simulation_export

urlpatterns = [
    path("", simulation_create, name="simulation-create"),
    path("<str:simulation_id>/", simulation_detail, name="simulation-detail"),
    path("<str:simulation_id>/stops/", simulation_stops, name="simulation-stops"),
    path("<str:simulation_id>/export/", simulation_export, name="simulation-export"),
]