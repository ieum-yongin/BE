
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import BusRoute, RoutePattern, RouteStop
from .serializers import RouteDetailSerializer, RouteListItemSerializer, RouteListQuerySerializer


def get_patterns_with_stops(route_ids):
    # 노선별 운행 패턴과 경유 정류소를 조회

    patterns = list(
        RoutePattern.objects
        .filter(route_id__in=route_ids)
        .order_by("route_id", "pattern_id")
    )

    pattern_ids = [pattern.pattern_id for pattern in patterns]

    route_stops = (
        RouteStop.objects
        .filter(pattern_id__in=pattern_ids)
        .select_related("stop")
        .order_by("pattern_id", "stop_sequence")
    )

    stops_by_pattern = {
        pattern_id: [] for pattern_id in pattern_ids
    }

    for route_stop in route_stops:
        stops_by_pattern[route_stop.pattern_id].append(
            route_stop
        )

    patterns_by_route = {
        route_id: [] for route_id in route_ids
    }

    for pattern in patterns:
        patterns_by_route[pattern.route_id].append(pattern)

    return patterns_by_route, stops_by_pattern


def get_representative_pattern(patterns):
    # 상행 -> 하행 순서로 선택

    up_pattern = next(
        (
            pattern
            for pattern in patterns
            if pattern.direction_name in ("상행", "UP")
        ),
        None,
    )

    down_pattern = next(
        (
            pattern
            for pattern in patterns
            if pattern.direction_name in ("하행", "DOWN")
        ),
        None,
    )

    return (
        up_pattern
        or down_pattern
        or (patterns[0] if patterns else None)
    )


@api_view(["GET"])
def route_list(request):
    query = RouteListQuerySerializer(
        data=request.query_params.dict()
    )

    if not query.is_valid():
        return Response(
            {
                "code": "INVALID_REQUEST",
                "message": "요청 값을 확인해 주세요.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    search = query.validated_data["q"]
    page = query.validated_data["page"]
    page_size = query.validated_data["page_size"]

    # 노선번호 부분 일치 검색
    routes = (
        BusRoute.objects
        .filter(route_number__contains=search)
        .order_by("route_number", "route_id")
    )

    count = routes.count()

    offset = (page - 1) * page_size
    routes = list(routes[offset:offset + page_size])

    route_ids = [route.route_id for route in routes]

    patterns_by_route, stops_by_pattern = (get_patterns_with_stops(route_ids))

    results = []

    for route in routes:
        representative = get_representative_pattern(patterns_by_route[route.route_id])

        representative_stops = (
            stops_by_pattern[representative.pattern_id]
            if representative is not None
            else []
        )

        results.append(
            {
                "id": route.route_id,
                "route_number": route.route_number,
                "start_stop_name": (
                    representative_stops[0].stop.name
                    if representative_stops else None
                ),
                "end_stop_name": (
                    representative_stops[-1].stop.name
                    if representative_stops else None
                ),
                "stop_count": (
                    len(representative_stops)
                    if representative is not None
                    else None
                ),
            }
        )

    return Response(
        {
            "count": count,
            "page": page,
            "page_size": page_size,
            "results": RouteListItemSerializer(
                results,
                many=True,
            ).data,
        }
    )


@api_view(["GET"])
def route_detail(request, route_id):
    route = BusRoute.objects.filter(
        route_id=route_id
    ).first()

    if route is None:
        return Response(
            {
                "code": "ROUTE_NOT_FOUND",
                "message": "해당 노선이 존재하지 않습니다.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    patterns_by_route, stops_by_pattern = (
        get_patterns_with_stops([route_id])
    )

    representative = get_representative_pattern(
        patterns_by_route[route_id]
    )

    pattern_data = None

    if representative is not None:
        route_stops = stops_by_pattern[
            representative.pattern_id
        ]

        stops = []

        for route_stop in route_stops:
            stop = route_stop.stop

            stops.append(
                {
                    "id": stop.id,
                    "name": stop.name,
                    "sequence": route_stop.stop_sequence,
                    "latitude": (
                        float(stop.latitude)
                        if stop.latitude is not None
                        else None
                    ),
                    "longitude": (
                        float(stop.longitude)
                        if stop.longitude is not None
                        else None
                    ),
                }
            )

        pattern_data = {
            "id": representative.pattern_id,
            "start_stop_name": (
                stops[0]["name"] if stops else None
            ),
            "end_stop_name": (
                stops[-1]["name"] if stops else None
            ),
            "stop_count": len(stops),
            "stops": stops,
        }

    result = {
        "id": route.route_id,
        "route_number": route.route_number,
        "pattern": pattern_data,
    }

    return Response(RouteDetailSerializer(result).data)
