from django.urls import path

from .views import route_detail, route_list

urlpatterns = [
    path("", route_list, name="route-list"),
    path("<int:route_id>/", route_detail, name="route-detail"),
]