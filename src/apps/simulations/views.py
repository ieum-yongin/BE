
import re

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.routes.models import BusRoute
from apps.stations.models import AnalysisRun, StopDiagnosis

from .models import Simulation
from .serializers import SimulationCreateSerializer, SimulationRouteSerializer, SimulationStopResultSerializer, SimulationStopsQuerySerializer, SimulationSummarySerializer
from .services import NetworkNotAvailable, NetworkRouteNotFound, create_simulation, get_changed_stops, get_simulation_routes, get_simulation_summary


MAX_BIGINT = 9223372036854775807


def invalid_request():
    return Response(
        {
            "code": "INVALID_REQUEST",
            "message": "요청 값을 확인해 주세요.",
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def parse_simulation_id(value):
    if not re.fullmatch(r"[0-9]+", value):
        return None

    normalized = value.lstrip("0")

    if not normalized:
        return None

    if len(normalized) > 19:
        return None

    simulation_id = int(normalized)

    if simulation_id > MAX_BIGINT:
        return None

    return simulation_id


def lookup_simulation(simulation_id):
    parsed_id = parse_simulation_id(simulation_id)

    if parsed_id is None:
        return None, invalid_request()

    simulation = Simulation.objects.filter(
        pk=parsed_id
    ).first()

    if simulation is None:
        return None, Response(
            {
                "code": "SIMULATION_NOT_FOUND",
                "message": "시뮬레이션이 존재하지 않습니다.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return simulation, None


@api_view(["POST"])
def simulation_create(request):
    # 1. 요청 검증
    if request.query_params:
        return invalid_request()

    serializer = SimulationCreateSerializer(
        data=request.data
    )

    if not serializer.is_valid():
        return invalid_request()

    route_ids = serializer.validated_data["route_ids"]

    # 2. 노선 존재 여부 확인
    existing_ids = set(
        BusRoute.objects.filter(
            pk__in=route_ids
        ).values_list("pk", flat=True)
    )

    if set(route_ids) != existing_ids:
        return Response(
            {
                "code": "ROUTE_NOT_FOUND",
                "message": "존재하지 않는 노선이 포함되어 있습니다.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    # 3. 최신 완료 분석 조회
    analysis = AnalysisRun.latest_completed()

    if analysis is None:
        return Response(
            {
                "code": "ANALYSIS_NOT_AVAILABLE",
                "message": "완료된 분석 결과가 없습니다.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    # 4. 기준 분석 데이터 확인
    if not StopDiagnosis.objects.filter(
        analysis_id=analysis.pk
    ).exists():
        return Response(
            {
                "code": "ANALYSIS_NOT_AVAILABLE",
                "message": "정류소 분석 데이터가 준비되지 않았습니다.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    # 5. AI 실행 및 결과 저장
    try:
        simulation = create_simulation(
            analysis=analysis,
            route_ids=route_ids,
        )
    except (NetworkNotAvailable, NetworkRouteNotFound):
        return Response(
            {
                "code": "NETWORK_NOT_AVAILABLE",
                "message": "기준 노선망을 사용할 수 없습니다.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    # 6. 성공 응답
    return Response(
        {
            "id": simulation.pk,
            "status": simulation.status,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
def simulation_detail(request, simulation_id):
    # 1. 요청 검증 및 시뮬레이션 조회
    if request.query_params or request.body:
        return invalid_request()

    simulation, error = lookup_simulation(simulation_id)

    if error is not None:
        return error

    # 2. 중단 노선 조회
    routes = get_simulation_routes(simulation)

    # 3. 완료된 경우에만 요약 결과 조회
    summary = None

    if simulation.status == "COMPLETED":
        result = get_simulation_summary(simulation)
        summary = SimulationSummarySerializer(result).data

    # 4. 응답 반환
    return Response(
        {
            "id": simulation.pk,
            "status": simulation.status,
            "routes": SimulationRouteSerializer(
                routes,
                many=True,
            ).data,
            "summary": summary,
        }
    )


@api_view(["GET"])
def simulation_stops(request, simulation_id):
    # 1. 요청값 검증
    if (
        request.body
        or any(
            key not in ("page", "page_size")
            for key in request.query_params
        )
    ):
        return invalid_request()

    query = SimulationStopsQuerySerializer(
        data=request.query_params.dict()
    )

    if not query.is_valid():
        return invalid_request()

    # 2. 시뮬레이션 조회
    simulation, error = lookup_simulation(simulation_id)

    if error is not None:
        return error

    # 3. 완료 여부 확인
    if simulation.status != "COMPLETED":
        return Response(
            {
                "code": "SIMULATION_NOT_COMPLETED",
                "message": "시뮬레이션 분석이 완료되지 않았습니다.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    # 4. 위험도가 변경된 정류소 조회
    results = get_changed_stops(simulation)

    # 5. 페이지네이션
    page = query.validated_data["page"]
    page_size = query.validated_data["page_size"]

    count = results.count()
    offset = (page - 1) * page_size

    page_results = (
        results[offset:offset + page_size]
        if offset < count
        else []
    )

    # 6. 응답 반환
    return Response(
        {
            "count": count,
            "page": page,
            "page_size": page_size,
            "results": SimulationStopResultSerializer(
                page_results,
                many=True,
            ).data,
        }
    )
