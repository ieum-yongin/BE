from rest_framework import serializers

from apps.pagination import PageQuerySerializer


class SimulationCreateSerializer(serializers.Serializer):
    route_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def validate_route_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate route IDs are not allowed.")
        return value


class SimulationStopsQuerySerializer(PageQuerySerializer):
    pass


class SimulationRouteSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="route_id")
    route_number = serializers.CharField(source="route.route_number")


class SimulationSummarySerializer(serializers.Serializer):
    danger_stop_count = serializers.IntegerField()
    caution_stop_count = serializers.IntegerField()
    estimated_affected_daily = serializers.FloatField(allow_null=True)


class SimulationStopResultSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="stop_id")
    name = serializers.CharField(source="stop.name")

    latitude = serializers.FloatField(
        source="stop.latitude",
        allow_null=True,
    )
    longitude = serializers.FloatField(
        source="stop.longitude",
        allow_null=True,
    )

    before_risk_level = serializers.CharField()
    after_risk_level = serializers.CharField()

    remaining_route_count = serializers.IntegerField(allow_null=True)
    after_min_alternatives = serializers.IntegerField(allow_null=True)
    estimated_affected_daily = serializers.FloatField(allow_null=True)

    is_isolated = serializers.BooleanField(allow_null=True)
    reason = serializers.CharField(allow_null=True)