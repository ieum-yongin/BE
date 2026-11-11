from django.urls import path

from .views import alert_detail, alert_list, alert_review_create

urlpatterns = [
    path("", alert_list, name="alert-list"),
    path("<str:alert_id>/", alert_detail, name="alert-detail"),
    path("<str:alert_id>/reviews/", alert_review_create, name="alert-review-create"),
]
