from django.db import models


class BusStop(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="stop_id")
    name = models.CharField(max_length=200)
    stop_number = models.CharField(max_length=20, null=True)
    direction_label = models.CharField(max_length=120, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    district_name = models.CharField(max_length=50, null=True)
    neighborhood_name = models.CharField(max_length=50, null=True)
    road_address = models.CharField(max_length=255, null=True)

    class Meta:
        managed = False
        db_table = "bus_stop"


class AnalysisRun(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="analysis_id")
    status = models.CharField(max_length=20)
    completed_at = models.DateTimeField(null=True)
    usage_batch_id = models.BigIntegerField()
    period_start = models.DateField()
    period_end = models.DateField()

    @classmethod
    def latest_completed(cls):
        return cls.objects.filter(status="COMPLETED").order_by("-completed_at", "-id").first()

    class Meta:
        managed = False
        db_table = "analysis_run"


class StopDiagnosis(models.Model):
    pk = models.CompositePrimaryKey("analysis_id", "stop_id")
    analysis_id = models.BigIntegerField()
    stop_id = models.BigIntegerField()
    risk_level = models.CharField(max_length=20)
    risk_reason = models.CharField(max_length=500, null=True)
    average_daily_boarding = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    serving_route_count = models.IntegerField(null=True)
    passengers_per_route = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    min_alternative_routes = models.IntegerField(null=True)

    class Meta:
        managed = False
        db_table = "stop_diagnosis"


class StopDailyUsage(models.Model):
    pk = models.CompositePrimaryKey("batch_id", "stop_id", "service_date")
    batch_id = models.BigIntegerField()
    stop_id = models.BigIntegerField()
    service_date = models.DateField()
    boarding_count = models.IntegerField()

    class Meta:
        managed = False
        db_table = "stop_daily_usage"
