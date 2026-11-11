from django.db import models


class BusStop(models.Model):
    id = models.BigAutoField(primary_key=True, db_column="stop_id")
    name = models.CharField(max_length=200)
    stop_number = models.CharField(max_length=20, null=True)
    direction_label = models.CharField(max_length=120, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)

    class Meta:
        managed = False
        db_table = "bus_stop"
