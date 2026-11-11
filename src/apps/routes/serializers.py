from rest_framework import serializers


class RouteListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        trim_whitespace=True,
    )
    page = serializers.RegexField(
        r"\A[0-9]+\Z",
        required=False,
        default=1,
    )
    page_size = serializers.RegexField(
        r"\A[0-9]+\Z",
        required=False,
        default=20,
    )

    def validate_page(self, value):
        return self._positive_integer(value)

    def validate_page_size(self, value):
        page_size = self._positive_integer(value)

        if page_size > 100:
            raise serializers.ValidationError("Must be at most 100.")

        return page_size

    @staticmethod
    def _positive_integer(value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Must be a positive integer.")

        if number < 1:
            raise serializers.ValidationError("Must be a positive integer.")

        return number


class RouteListItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    route_number = serializers.CharField()
    start_stop_name = serializers.CharField(allow_null=True)
    end_stop_name = serializers.CharField(allow_null=True)
    stop_count = serializers.IntegerField(allow_null=True)


class RouteStopSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sequence = serializers.IntegerField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)


class RoutePatternSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    start_stop_name = serializers.CharField(allow_null=True)
    end_stop_name = serializers.CharField(allow_null=True)
    stop_count = serializers.IntegerField()
    stops = RouteStopSerializer(many=True)


class RouteDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    route_number = serializers.CharField()
    pattern = RoutePatternSerializer(allow_null=True)
