import re
from collections import Counter
from datetime import timedelta
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


def lookup_station(request, station_id):
    station_id = station_id.lstrip("0")
    if (
        not re.fullmatch(r"[0-9]+", station_id)
        or request.query_params
        or request.body
    ):
        return None, Response(
            {"code": "INVALID_REQUEST", "message": "요청 값을 확인해 주세요."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # A signed BIGINT can hold at most 19 decimal digits.
    station = BusStop.objects.filter(pk=int(station_id)).first() if len(station_id) <= 19 else None
    if station is None:
        return None, Response(
            {"code": "STATION_NOT_FOUND", "message": "정류장이 존재하지 않습니다."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return station, None


@api_view(["GET"])
def station_detail(request, station_id):
    station, error = lookup_station(request, station_id)
    if error is not None:
        return error

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


WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
STOP_PROFILES = {
    "DEPARTURE": "DEPARTURE",
    "ARRIVAL": "ARRIVAL",
    "BALANCED": "BALANCED",
    "출발형": "DEPARTURE",
    "도착형": "ARRIVAL",
    "균형형": "BALANCED",
}


@api_view(["GET"])
def station_usage(request, station_id):
    station, error = lookup_station(request, station_id)
    if error is not None:
        return error

    result = {
        "station_id": station.pk,
        "period_start": None,
        "period_end": None,
        "average_daily_boarding": None,
        "average_daily_alighting": None,
        "city_boarding_rank": None,
        "boarding_ratio": None,
        "transfer_ratio": None,
        "stop_profile": None,
        "weekly_usage": [],
        "weekday_usage": [],
    }
    analysis = AnalysisRun.latest_completed()
    if analysis is None:
        return Response(result)

    daily_usage = list(
        StopDailyUsage.objects.filter(
            batch_id=analysis.usage_batch_id,
            stop_id=station.pk,
            service_date__range=(analysis.period_start, analysis.period_end),
        ).values_list(
            "service_date", "boarding_count", "alighting_count", "transfer_boarding_count",
        )
    )
    if not daily_usage:
        return Response(result)

    weekly_boardings = Counter()
    weekly_alightings = Counter()
    weekday_boardings = Counter()
    weekday_observations = Counter()
    for service_date, boardings, alightings, _ in daily_usage:
        weekday = service_date.weekday()
        week_start = service_date - timedelta(days=weekday)
        weekly_boardings[week_start] += boardings
        weekly_alightings[week_start] += alightings
        weekday_boardings[weekday] += boardings
        weekday_observations[weekday] += 1

    total_boardings = weekly_boardings.total()
    total_alightings = weekly_alightings.total()
    total_usage = total_boardings + total_alightings
    diagnosis = StopDiagnosis.objects.filter(pk=(analysis.pk, station.pk)).first()
    transfer_ratio = diagnosis.transfer_ratio if diagnosis else None
    transfer_counts = [row[3] for row in daily_usage]
    if transfer_ratio is None and total_boardings and None not in transfer_counts:
        transfer_ratio = sum(transfer_counts) / total_boardings

    result.update(
        period_start=analysis.period_start.isoformat(),
        period_end=analysis.period_end.isoformat(),
        average_daily_boarding=total_boardings / len(daily_usage),
        average_daily_alighting=total_alightings / len(daily_usage),
        city_boarding_rank=diagnosis.city_boarding_rank if diagnosis else None,
        boarding_ratio=total_boardings / total_usage if total_usage else None,
        transfer_ratio=float(transfer_ratio) if transfer_ratio is not None else None,
        stop_profile=STOP_PROFILES.get(diagnosis.stop_profile) if diagnosis else None,
        weekly_usage=[
            {
                "week_start": week_start.isoformat(),
                "boarding_count": weekly_boardings[week_start],
                "alighting_count": weekly_alightings[week_start],
            }
            for week_start in sorted(weekly_boardings)
        ],
        weekday_usage=[
            {
                "weekday": WEEKDAYS[weekday],
                "average_boarding": weekday_boardings[weekday] / weekday_observations[weekday],
            }
            for weekday in sorted(weekday_observations)
        ],
    )
    return Response(result)
