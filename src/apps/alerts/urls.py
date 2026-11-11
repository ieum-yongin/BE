from django.urls import path

from .views import alert_detail, alert_list

urlpatterns = [
    path("", alert_list, name="alert-list"),
    path("<str:alert_id>/", alert_detail, name="alert-detail"),
]
