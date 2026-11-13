"""이음 — '만약에' 시뮬레이션.

노선을 운행 중단했을 때 정류소별 위험도가 어떻게 바뀌는지 계산한다.

사용 흐름 (백엔드)
    1. 서버 시작 시 Network를 한 번 만들어 둔다 (network_id별 캐시).
    2. POST /api/simulations/ 요청이 오면 simulate(network, routes_off)를 호출한다.
    3. 반환값을 simulation_stop_result에 저장하고 simulation.status를 완료로 바꾼다.

이 모듈은 DB에 읽거나 쓰지 않는다. 입력은 순수 파이썬 값, 출력은 dict다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

# API 명세와 같은 값
SAFE = "SAFE"
CAUTION = "CAUTION"
DANGER = "DANGER"
UNKNOWN = "UNKNOWN"

_RISK_ORDER = {UNKNOWN: -1, SAFE: 0, CAUTION: 1, DANGER: 2}


@dataclass(frozen=True)
class RiskCriteria:
    """위험도 판정 기준. 값은 임시 기준이며, 확정되면 여기만 바꾸면 된다.

    판정 순서
        - 지나는 노선 0개           → DANGER (고립)
        - 노선 1개 + 하루 승차 많음  → DANGER (그 노선이 멈추면 많은 사람이 발이 묶임)
        - 노선 1개 (이용 적음)      → CAUTION
        - 노선 few_routes개 이하    → CAUTION
        - 노선당 승차가 많음         → CAUTION
        - 그 외                     → SAFE
    """

    busy_daily_boarding: float = 100.0      # '이용 많음' 기준 (명/일)
    few_routes: int = 2                      # '노선 적음' 기준 (개)
    high_passengers_per_route: float = 300.0 # '노선당 승차 많음' 기준 (명/일/노선)

    def as_dict(self) -> dict:
        return {
            "busy_daily_boarding": self.busy_daily_boarding,
            "few_routes": self.few_routes,
            "high_passengers_per_route": self.high_passengers_per_route,
        }


def classify_risk(route_count: int, daily_boarding: float | None,
                  criteria: RiskCriteria = RiskCriteria()) -> str:
    """정류소 하나의 위험 등급을 매긴다."""
    boarding = daily_boarding or 0.0
    if route_count <= 0:
        return DANGER
    if route_count == 1:
        return DANGER if boarding >= criteria.busy_daily_boarding else CAUTION
    if route_count <= criteria.few_routes:
        return CAUTION
    if boarding / route_count >= criteria.high_passengers_per_route:
        return CAUTION
    return SAFE


@dataclass
class Network:
    """시뮬레이션에 필요한 노선망. 서버 시작 시 한 번 만들어 재사용한다.

    route_stops : 노선 ID → 그 노선이 지나는 정류소 ID 목록 (방향·운행경로는 합쳐서 노선 단위로)
    daily_boarding : 정류소 ID → 하루 평균 승차 (stop_diagnosis.average_daily_boarding)
    is_complete : 마을버스까지 포함된 노선망인지 (network_snapshot). False면 결과에 임시 표시
    """

    network_id: int
    route_stops: Mapping[int, Iterable[int]]
    daily_boarding: Mapping[int, float] = field(default_factory=dict)
    is_complete: bool = False

    def __post_init__(self) -> None:
        self._route_stops: dict[int, frozenset[int]] = {
            r: frozenset(stops) for r, stops in self.route_stops.items()
        }
        stop_routes: dict[int, set[int]] = {}
        for route_id, stops in self._route_stops.items():
            for stop_id in stops:
                stop_routes.setdefault(stop_id, set()).add(route_id)
        self._stop_routes = {s: frozenset(r) for s, r in stop_routes.items()}

    @property
    def route_ids(self) -> frozenset[int]:
        return frozenset(self._route_stops)

    def routes_at(self, stop_id: int) -> frozenset[int]:
        return self._stop_routes.get(stop_id, frozenset())

    def stops_on(self, route_id: int) -> frozenset[int]:
        return self._route_stops.get(route_id, frozenset())


def build_network(network_id: int,
                  route_stop_rows: Iterable[tuple[int, int]],
                  boarding_rows: Iterable[tuple[int, float]] = (),
                  is_complete: bool = False) -> Network:
    """DB 조회 결과로 Network를 만든다.

    route_stop_rows : (route_id, stop_id) 쌍. 예) Django
        RouteStop.objects.filter(pattern__network_id=nid)
                 .values_list("pattern__route_id", "stop_id")
    boarding_rows : (stop_id, average_daily_boarding) 쌍. 예)
        StopDiagnosis.objects.filter(analysis_id=aid)
                     .values_list("stop_id", "average_daily_boarding")
    """
    route_stops: dict[int, set[int]] = {}
    for route_id, stop_id in route_stop_rows:
        route_stops.setdefault(int(route_id), set()).add(int(stop_id))
    boarding = {int(s): float(b) for s, b in boarding_rows if b is not None}
    return Network(network_id=network_id, route_stops=route_stops,
                   daily_boarding=boarding, is_complete=is_complete)


def simulate(network: Network, routes_off: Iterable[int],
             criteria: RiskCriteria = RiskCriteria()) -> dict:
    """노선을 운행 중단했을 때 정류소별 변화를 계산한다.

    Parameters
    ----------
    network : Network
    routes_off : 운행 중단할 노선 ID 목록 (simulation_route_change.route_id)
    criteria : 위험도 기준 (기본값: 임시 기준)

    Returns
    -------
    dict
        summary : 위험·주의 증가 수, 영향 승객, 고립 정류소 수 등
        stops   : 중단 노선이 지나던 정류소별 결과 (simulation_stop_result 한 행씩)
        unknown_route_ids : 노선망에 없는 노선 ID (무시됨)
        is_provisional : 노선망이 불완전하면 True
        criteria : 사용한 기준값 (simulation.parameters_json에 저장 권장)
    """
    requested = {int(r) for r in routes_off}
    off = requested & network.route_ids
    unknown = sorted(requested - off)

    affected_stop_ids: set[int] = set()
    for route_id in off:
        affected_stop_ids |= network.stops_on(route_id)

    stops: list[dict] = []
    danger_delta = caution_delta = isolated_count = 0
    affected_riders = 0.0

    for stop_id in sorted(affected_stop_ids):
        before_routes = network.routes_at(stop_id)
        after_routes = before_routes - off
        before_n, after_n = len(before_routes), len(after_routes)
        boarding = network.daily_boarding.get(stop_id)

        before_level = classify_risk(before_n, boarding, criteria)
        after_level = classify_risk(after_n, boarding, criteria)

        # 영향 승객 추정: 하루 승차 × (멈춘 노선 수 / 원래 노선 수)
        # 노선별 승차 데이터가 없어서 노선마다 이용이 같다고 가정한 근사값
        lost = before_n - after_n
        estimated = (boarding or 0.0) * lost / before_n if before_n else 0.0
        is_isolated = before_n > 0 and after_n == 0

        affected_riders += estimated
        isolated_count += is_isolated
        danger_delta += (after_level == DANGER) - (before_level == DANGER)
        caution_delta += (after_level == CAUTION) - (before_level == CAUTION)

        stops.append({
            "stop_id": stop_id,
            "before_risk_level": before_level,
            "after_risk_level": after_level,
            "is_changed": before_level != after_level,
            "before_route_count": before_n,
            "remaining_route_count": after_n,
            # 남은 노선 중 하나가 더 멈췄을 때 남는 대체 노선 수
            "after_min_alternatives": max(after_n - 1, 0),
            "estimated_affected_daily": round(estimated, 1),
            "is_isolated": is_isolated,
            "reason": _reason(before_n, after_n, lost, boarding, after_level),
        })

    # 화면용 정렬: 등급이 나빠진 곳 → 영향 승객 많은 곳 순
    stops.sort(key=lambda s: (
        -(_RISK_ORDER[s["after_risk_level"]] - _RISK_ORDER[s["before_risk_level"]]),
        -s["estimated_affected_daily"],
    ))

    return {
        "summary": {
            "routes_off": sorted(off),
            "affected_stop_count": len(stops),
            "changed_stop_count": sum(s["is_changed"] for s in stops),
            "danger_delta": danger_delta,
            "caution_delta": caution_delta,
            "isolated_stop_count": isolated_count,
            "affected_riders": round(affected_riders),
        },
        "stops": stops,
        "unknown_route_ids": unknown,
        "is_provisional": not network.is_complete,
        "criteria": criteria.as_dict(),
    }


def _reason(before_n: int, after_n: int, lost: int,
            boarding: float | None, after_level: str) -> str:
    riders = f"하루 승차 약 {round(boarding):,}명" if boarding else "이용량 정보 없음"
    if after_n == 0:
        return f"지나던 노선 {before_n}개가 모두 중단되어 고립 · {riders}"
    if after_n == 1 and after_level == DANGER:
        return f"노선 {lost}개 중단으로 1개만 남음 · {riders}"
    return f"노선 {before_n}개 → {after_n}개 · {riders}"
