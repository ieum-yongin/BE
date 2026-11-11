from django.db import models

from apps.stations.models import AnalysisRun, BusStop


class UsageAlert(models.Model):
    class Classification(models.TextChoices):
        NEEDS_CHECK = "NEEDS_CHECK"
        EXPECTED = "EXPECTED"

    class ReviewStatus(models.TextChoices):
        NEW = "NEW"
        REVIEWING = "REVIEWING"
        RESOLVED = "RESOLVED"

    id = models.BigAutoField(primary_key=True, db_column="alert_id")
    analysis = models.ForeignKey(AnalysisRun, models.DO_NOTHING, db_column="analysis_id")
    station = models.ForeignKey(BusStop, models.DO_NOTHING, db_column="stop_id")
    change_start = models.DateField()
    change_end = models.DateField()
    change_direction = models.CharField(max_length=10)
    classification = models.CharField(max_length=20, choices=Classification.choices)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices)
    usage_ratio = models.DecimalField(max_digits=9, decimal_places=4, null=True)
    consecutive_days = models.IntegerField()
    baseline_daily_usage = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    observed_daily_usage = models.DecimalField(max_digits=12, decimal_places=2)
    expected_reason = models.CharField(max_length=200, null=True)
    analysis_summary = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "usage_alert"


class AlertDailyDetail(models.Model):
    pk = models.CompositePrimaryKey("alert_id", "service_date")
    alert_id = models.BigIntegerField()
    service_date = models.DateField()
    baseline_usage = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    observed_usage = models.IntegerField(null=True)
    is_anomalous = models.BooleanField()

    class Meta:
        managed = False
        db_table = "alert_daily_detail"


class AlertReview(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="review_id")
    alert_id = models.BigIntegerField()
    status_after = models.CharField(max_length=20)
    note = models.TextField(null=True)
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "alert_review"
