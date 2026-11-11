from django.urls import path

from .views import simulation_create, simulation_detail, simulation_stops

urlpatterns = [
    path("", simulation_create, name="simulation-create"),
    path("<str:simulation_id>/", simulation_detail, name="simulation-detail"),
    path("<str:simulation_id>/stops/", simulation_stops, name="simulation-stops"),
]