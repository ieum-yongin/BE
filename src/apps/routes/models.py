
from django.db import models


class BusCompany(models.Model):
    company_id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = "bus_company"

    def __str__(self):
        return self.name


class BusRoute(models.Model):
    route_id = models.BigAutoField(primary_key=True)

    operator = models.ForeignKey(
        BusCompany,
        on_delete=models.DO_NOTHING,
        db_column="operator_id",
        related_name="routes",
    )

    source_system = models.CharField(max_length=30)
    source_route_id = models.CharField(max_length=30)
    route_number = models.CharField(max_length=30)
    route_type = models.CharField(max_length=30)

    class Meta:
        managed = False
        db_table = "bus_route"
        unique_together = (("source_system", "source_route_id"),)
        ordering = ["route_number", "route_id"]

    def __str__(self):
        return self.route_number


class RoutePattern(models.Model):
    pattern_id = models.BigIntegerField(primary_key=True)

    network_id = models.BigIntegerField()

    route = models.ForeignKey(
        BusRoute,
        on_delete=models.DO_NOTHING,
        db_column="route_id",
        related_name="patterns",
    )

    pattern_code = models.CharField(max_length=40)
    direction_name = models.CharField(max_length=100)
    first_departure = models.TimeField(null=True, blank=True)
    last_departure = models.TimeField(null=True, blank=True)
    headway_minutes = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "route_pattern"
        unique_together = (("network_id", "route", "pattern_code"),)


class RouteStop(models.Model):
    pk = models.CompositePrimaryKey(
        "pattern_id",
        "stop_sequence",
    )

    pattern = models.ForeignKey(
        RoutePattern,
        on_delete=models.DO_NOTHING,
        db_column="pattern_id",
        related_name="route_stops",
    )

    stop_sequence = models.IntegerField()

    stop = models.ForeignKey(
        "stations.BusStop",
        on_delete=models.DO_NOTHING,
        db_column="stop_id",
        related_name="route_stops",
    )

    distance_from_start_m = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    class Meta:
        managed = False
        db_table = "route_stop"
        ordering = ["stop_sequence"]