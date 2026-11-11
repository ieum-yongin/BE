from django.urls import path

from .views import alert_list

urlpatterns = [
    path("", alert_list, name="alert-list"),
]
