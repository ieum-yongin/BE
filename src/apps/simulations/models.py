from django.db import models
from django.utils import timezone


class Simulation(models.Model):
    simulation_id = models.BigAutoField(primary_key=True)

    baseline_analysis = models.ForeignKey(
        "stations.AnalysisRun",
        on_delete=models.DO_NOTHING,
        db_column="baseline_analysis_id",
        related_name="simulations",
    )

    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20)
    parameters_json = models.TextField()

    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "simulation"


class SimulationRouteChange(models.Model):
    pk = models.CompositePrimaryKey(
        "simulation_id",
        "route_id",
    )

    simulation = models.ForeignKey(
        Simulation,
        on_delete=models.DO_NOTHING,
        db_column="simulation_id",
        related_name="route_changes",
    )

    route = models.ForeignKey(
        "routes.BusRoute",
        on_delete=models.DO_NOTHING,
        db_column="route_id",
        related_name="simulation_changes",
    )

    change_type = models.CharField(max_length=20)

    class Meta:
        managed = False
        db_table = "simulation_route_change"


class SimulationStopResult(models.Model):
    pk = models.CompositePrimaryKey(
        "simulation_id",
        "stop_id",
    )

    simulation = models.ForeignKey(
        Simulation,
        on_delete=models.DO_NOTHING,
        db_column="simulation_id",
        related_name="stop_results",
    )

    stop = models.ForeignKey(
        "stations.BusStop",
        on_delete=models.DO_NOTHING,
        db_column="stop_id",
        related_name="simulation_results",
    )

    after_risk_level = models.CharField(max_length=20)
    remaining_route_count = models.IntegerField()

    after_min_alternatives = models.IntegerField(
        null=True,
        blank=True,
    )

    estimated_affected_daily = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    is_isolated = models.BooleanField()

    reason = models.CharField(
        max_length=500,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "simulation_stop_result"