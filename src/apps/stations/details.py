from collections import defaultdict
from decimal import Decimal
from math import asin, cos, degrees, radians, sin, sqrt

from django.db import connection
from django.db.models import Avg, FloatField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce

from .models import AnalysisRun, BusStop, StopDailyUsage, StopDiagnosis


EARTH_RADIUS_M = 6_371_008.8
NEARBY_RADIUS_M = 300


def with_station_usage(stations, analysis):
    if analysis is None:
        return stations.annotate(
            risk_level=Value("UNKNOWN"),
            average_daily_boarding=Value(None, output_field=FloatField()),
        )

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
    return stations.annotate(
        risk_level=Coalesce(Subquery(diagnosis.values("risk_level")), Value("UNKNOWN")),
        average_daily_boarding=Coalesce(
            Subquery(diagnosis.values("average_daily_boarding")),
            Subquery(daily_usage),
            output_field=FloatField(),
        ),
    )


def nearby_stations(station, analysis):
    latitude_delta = Decimal(str(degrees(NEARBY_RADIUS_M / EARTH_RADIUS_M)))
    candidates = BusStop.objects.filter(
        latitude__range=(station.latitude - latitude_delta, station.latitude + latitude_delta),
    ).exclude(pk=station.pk)
    candidates = with_station_usage(candidates, analysis).values_list(
        "id", "name", "latitude", "longitude", "average_daily_boarding",
    )

    origin_lat = radians(station.latitude)
    origin_lon = radians(station.longitude)
    results = []
    for stop_id, name, latitude, longitude, boarding in candidates:
        latitude = radians(latitude)
        longitude = radians(longitude)
        haversine = (
            sin((latitude - origin_lat) / 2) ** 2
            + cos(origin_lat) * cos(latitude) * sin((longitude - origin_lon) / 2) ** 2
        )
        distance = 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, haversine)))
        if distance <= NEARBY_RADIUS_M:
            results.append({
                "id": stop_id,
                "name": name,
                "distance_m": distance,
                "average_daily_boarding": boarding,
            })
    return sorted(results, key=lambda result: (result["distance_m"], result["id"]))


def serving_routes(cursor, station_id, analysis_id):
    cursor.execute(
        """
        SELECT DISTINCT route.route_id, route.route_number, route.route_type
        FROM bus_route AS route
        JOIN route_pattern AS pattern ON pattern.route_id = route.route_id
        JOIN route_stop AS stop ON stop.pattern_id = pattern.pattern_id
        WHERE stop.stop_id = %s AND pattern.network_id = COALESCE(
            (SELECT network_id FROM analysis_run WHERE analysis_id = %s),
            (SELECT network_id FROM network_snapshot ORDER BY effective_date DESC, network_id DESC LIMIT 1)
        )
        ORDER BY route.route_id
        """,
        [station_id, analysis_id],
    )
    return [
        {"id": route_id, "route_number": number, "route_type": route_type}
        for route_id, number, route_type in cursor.fetchall()
    ]


def hub_access(cursor, station_id, analysis_id):
    cursor.execute(
        """
        SELECT direct.hub_id, route.route_id, route.route_number
        FROM stop_hub_direct_route AS direct
        JOIN bus_route AS route ON route.route_id = direct.route_id
        WHERE direct.analysis_id = %s AND direct.stop_id = %s
        ORDER BY route.route_id
        """,
        [analysis_id, station_id],
    )
    direct_routes = defaultdict(list)
    for hub_id, route_id, number in cursor.fetchall():
        direct_routes[hub_id].append({"id": route_id, "route_number": number})

    cursor.execute(
        """
        SELECT hub.hub_id, hub.name, access.is_reachable, access.minimum_transfers
        FROM stop_hub_access AS access
        JOIN major_hub AS hub ON hub.hub_id = access.hub_id
        WHERE access.analysis_id = %s AND access.stop_id = %s
        ORDER BY hub.hub_id
        """,
        [analysis_id, station_id],
    )
    return [
        {
            "id": hub_id,
            "name": name,
            "is_reachable": bool(reachable),
            "minimum_transfers": transfers if reachable else None,
            "direct_routes": direct_routes[hub_id],
        }
        for hub_id, name, reachable, transfers in cursor.fetchall()
    ]


def route_overlaps(cursor, station_id, analysis_id):
    cursor.execute(
        """
        SELECT overlap.pattern_a_id, overlap.pattern_b_id,
               overlap.overlap_ratio_a, overlap.overlap_ratio_b
        FROM route_overlap AS overlap
        WHERE overlap.analysis_id = %s
          AND EXISTS (
              SELECT 1 FROM route_stop AS stop
              WHERE stop.stop_id = %s
                AND stop.pattern_id IN (overlap.pattern_a_id, overlap.pattern_b_id)
          )
        ORDER BY overlap.pattern_a_id, overlap.pattern_b_id
        """,
        [analysis_id, station_id],
    )
    return [
        {
            "pattern_a_id": pattern_a,
            "pattern_b_id": pattern_b,
            "overlap_ratio_a": float(ratio_a),
            "overlap_ratio_b": float(ratio_b),
        }
        for pattern_a, pattern_b, ratio_a, ratio_b in cursor.fetchall()
    ]


def station_details_data(station):
    analysis = AnalysisRun.latest_completed()
    analysis_id = analysis.pk if analysis is not None else None
    nearby = nearby_stations(station, analysis)

    with connection.cursor() as cursor:
        routes = serving_routes(cursor, station.pk, analysis_id)
        hubs = hub_access(cursor, station.pk, analysis_id) if analysis is not None else []
        overlaps = route_overlaps(cursor, station.pk, analysis_id) if analysis is not None else []

    return {
        "station_id": station.pk,
        "nearby_stations": nearby,
        "hubs": hubs,
        "routes": routes,
        "route_overlaps": overlaps,
    }
