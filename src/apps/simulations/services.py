
import json
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, CharField, Count, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.routes.models import RouteStop
from apps.stations.models import StopDiagnosis

from .models import Simulation, SimulationRouteChange, SimulationStopResult


class NetworkNotAvailable(Exception):
    pass


class NetworkRouteNotFound(Exception):
    pass


def create_simulation(analysis, route_ids):
    # 1. 기준 노선망의 노선-정류소 관계 조회
    route_stop_rows = list(
        RouteStop.objects.filter(
            pattern__network_id=analysis.network_id
        )
        .values_list("pattern__route_id", "stop_id")
        .distinct()
    )

    if not route_stop_rows:
        raise NetworkNotAvailable()

    # 2. 기존 분석의 정류소별 평균 승차량 조회
    boarding_rows = list(
        StopDiagnosis.objects.filter(
            analysis_id=analysis.pk
        ).values_list(
            "stop_id",
            "average_daily_boarding",
        )
    )

    # 3. AI 시뮬레이션 실행
    from ieum_ai.simulation import build_network, simulate

    network = build_network(
        network_id=analysis.network_id,
        route_stop_rows=route_stop_rows,
        boarding_rows=boarding_rows,
        is_complete=False,
    )

    result = simulate(
        network,
        routes_off=route_ids,
    )

    if result["unknown_route_ids"]:
        raise NetworkRouteNotFound()

    # 4. 시뮬레이션 관련 세 테이블에 결과 저장
    with transaction.atomic():
        simulation = Simulation.objects.create(
            baseline_analysis=analysis,
            title="노선 운행 중단 시뮬레이션",
            status="COMPLETED",
            parameters_json=json.dumps(
                {
                    "criteria": result["criteria"],
                },
                ensure_ascii=False,
            ),
            completed_at=timezone.now(),
        )

        # 중단 노선 저장
        SimulationRouteChange.objects.bulk_create([
            SimulationRouteChange(
                simulation=simulation,
                route_id=route_id,
                change_type="SUSPEND",
            )
            for route_id in route_ids
        ])

        # 정류소별 중단 후 위험도 및 분석 결과 저장
        SimulationStopResult.objects.bulk_create([
            SimulationStopResult(
                simulation=simulation,
                stop_id=stop["stop_id"],
                after_risk_level=stop["after_risk_level"],
                remaining_route_count=stop["remaining_route_count"],
                after_min_alternatives=stop["after_min_alternatives"],
                estimated_affected_daily=(
                    Decimal(str(stop["estimated_affected_daily"]))
                    if stop["estimated_affected_daily"] is not None
                    else None
                ),
                is_isolated=stop["is_isolated"],
                reason=stop["reason"],
            )
            for stop in result["stops"]
        ])

    return simulation


def get_simulation_routes(simulation):
    return (
        SimulationRouteChange.objects.filter(
            simulation=simulation
        )
        .select_related("route")
        .order_by("route_id")
    )


def get_simulation_summary(simulation):
    return (
        SimulationStopResult.objects.filter(
            simulation=simulation
        )
        .aggregate(
            danger_stop_count=Count(
                "stop_id",
                filter=Q(after_risk_level="DANGER"),
            ),
            caution_stop_count=Count(
                "stop_id",
                filter=Q(after_risk_level="CAUTION"),
            ),
            estimated_affected_daily=Sum(
                "estimated_affected_daily"
            ),
        )
    )


def get_changed_stops(simulation):
    # 1. 해당 시뮬레이션의 기준 분석 위험도 조회
    before_risk = StopDiagnosis.objects.filter(
        analysis_id=simulation.baseline_analysis_id,
        stop_id=OuterRef("stop_id"),
    ).values("risk_level")[:1]

    # 2. 시뮬레이션 결과에 기존 위험도 연결
    # 3. 위험도가 변경된 정류소만 필터링
    # 4. 변경 후 위험도 및 정류소 ID로 정렬
    return (
        SimulationStopResult.objects.filter(
            simulation=simulation
        )
        .select_related("stop")
        .annotate(
            before_risk_level=Coalesce(
                Subquery(before_risk),
                Value("UNKNOWN"),
                output_field=CharField(),
            )
        )
        .exclude(
            before_risk_level=F("after_risk_level")
        )
        .annotate(
            risk_order=Case(
                When(
                    after_risk_level="DANGER",
                    then=Value(0),
                ),
                When(
                    after_risk_level="CAUTION",
                    then=Value(1),
                ),
                When(
                    after_risk_level="SAFE",
                    then=Value(2),
                ),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by("risk_order", "stop_id")
    )


def get_simulation_report_stops(simulation):
    before_risk = StopDiagnosis.objects.filter(
        analysis_id=simulation.baseline_analysis_id,
        stop_id=OuterRef("stop_id"),
    ).values("risk_level")[:1]

    return (
        SimulationStopResult.objects.filter(
            simulation=simulation
        )
        .select_related("stop")
        .annotate(
            before_risk_level=Coalesce(
                Subquery(before_risk),
                Value("UNKNOWN"),
                output_field=CharField(),
            )
        )
        .annotate(
            changed_order=Case(
                When(
                    before_risk_level=F("after_risk_level"),
                    then=Value(1),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            risk_order=Case(
                When(after_risk_level="DANGER", then=Value(0)),
                When(after_risk_level="CAUTION", then=Value(1)),
                When(after_risk_level="SAFE", then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
        )
        .order_by(
            "changed_order",
            "risk_order",
            "stop_id",
        )
    )