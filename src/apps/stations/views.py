import re
from decimal import Decimal, InvalidOperation

from django.db.models import Avg, FloatField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import AnalysisRun, BusStop, StopDailyUsage, StopDiagnosis


class StationListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True, default="")
    page = serializers.RegexField(r"\A[0-9]+\Z", required=False, default=1)
    page_size = serializers.RegexField(r"\A[0-9]+\Z", required=False, default=20)

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
        except ValueError:
            raise serializers.ValidationError("Must be a positive integer.")
        if number < 1:
            raise serializers.ValidationError("Must be a positive integer.")
        return number


class StationListItemSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()

    class Meta:
        model = BusStop
        fields = ("id", "name", "stop_number", "direction_label", "latitude", "longitude")


@api_view(["GET"])
def station_list(request):
    query = StationListQuerySerializer(data=request.query_params.dict())
    if not query.is_valid():
        return Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    search = query.validated_data["q"]
    page = query.validated_data["page"]
    page_size = query.validated_data["page_size"]

    stations = BusStop.objects.order_by("name", "id")
    if search:
        stations = stations.filter(Q(name__icontains=search) | Q(stop_number__icontains=search))

    count = stations.count()
    offset = (page - 1) * page_size
    results = stations[offset:offset + page_size] if offset < count else []
    return Response({
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": StationListItemSerializer(results, many=True).data,
    })


class StationMapQuerySerializer(serializers.Serializer):
    bbox = serializers.CharField(required=False)

    def validate_bbox(self, value):
        error = serializers.ValidationError("Enter west,south,east,north in WGS84 coordinates.")
        try:
            west, south, east, north = map(Decimal, value.split(","))
        except (InvalidOperation, ValueError):
            raise error

        if not all(coordinate.is_finite() for coordinate in (west, south, east, north)):
            raise error
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise error
        return west, south, east, north


class StationMapItemSerializer(StationListItemSerializer):
    risk_level = serializers.CharField()
    average_daily_boarding = serializers.FloatField(allow_null=True)

    class Meta(StationListItemSerializer.Meta):
        fields = ("id", "name", "latitude", "longitude", "risk_level", "average_daily_boarding")


@api_view(["GET"])
def station_map(request):
    query = StationMapQuerySerializer(data=request.query_params.dict())
    if not query.is_valid():
        return Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    stations = BusStop.objects.order_by("id")
    if "bbox" in query.validated_data:
        west, south, east, north = query.validated_data["bbox"]
        stations = stations.filter(
            longitude__range=(west, east),
            latitude__range=(south, north),
        )

    analysis = AnalysisRun.latest_completed()
    if analysis is None:
        stations = stations.annotate(
            risk_level=Value("UNKNOWN"),
            average_daily_boarding=Value(None, output_field=FloatField()),
        )
    else:
        diagnosis = StopDiagnosis.objects.filter(analysis_id=analysis.pk, stop_id=OuterRef("pk"))
        daily_usage = (
            StopDailyUsage.objects.filter(
                batch_id=analysis.usage_batch_id,
                stop_id=OuterRef("pk"),
                service_date__range=(analysis.period_start, analysis.period_end),
            )
            .values("stop_id")
            .annotate(average=Avg("boarding_count"))
            .values("average")
        )
        stations = stations.annotate(
            risk_level=Coalesce(Subquery(diagnosis.values("risk_level")), Value("UNKNOWN")),
            average_daily_boarding=Coalesce(
                Subquery(diagnosis.values("average_daily_boarding")),
                Subquery(daily_usage),
                output_field=FloatField(),
            ),
        )
    return Response({"results": StationMapItemSerializer(stations, many=True).data})


class StationDetailSerializer(StationListItemSerializer):
    class Meta(StationListItemSerializer.Meta):
        fields = StationListItemSerializer.Meta.fields + (
            "district_name", "neighborhood_name", "road_address",
        )


class StationRiskMetricsSerializer(serializers.Serializer):
    serving_route_count = serializers.IntegerField(allow_null=True)
    passengers_per_route = serializers.FloatField(allow_null=True)
    min_alternative_routes = serializers.IntegerField(allow_null=True)


@api_view(["GET"])
def station_detail(request, station_id):
    station_id = station_id.lstrip("0")
    if (
        not re.fullmatch(r"[0-9]+", station_id)
        or request.query_params
        or request.body
    ):
        return Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # A signed BIGINT can hold at most 19 decimal digits.
    station = BusStop.objects.filter(pk=int(station_id)).first() if len(station_id) <= 19 else None
    if station is None:
        return Response(
            {"code": "STATION_NOT_FOUND", "message": "정류장이 존재하지 않습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )

    analysis = AnalysisRun.latest_completed()
    diagnosis = None
    if analysis is not None:
        diagnosis = StopDiagnosis.objects.filter(pk=(analysis.pk, station.pk)).first()

    return Response({
        **StationDetailSerializer(station).data,
        "risk_level": diagnosis.risk_level if diagnosis is not None else "UNKNOWN",
        "risk_reason": diagnosis.risk_reason if diagnosis is not None else None,
        "risk_metrics": StationRiskMetricsSerializer(diagnosis).data if diagnosis is not None else None,
    })
