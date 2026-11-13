import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Avg, Count

from apps.routes.models import RouteStop
from apps.stations.models import AnalysisRun, StopDailyUsage, StopDiagnosis
from ieum_ai.simulation import RiskCriteria, UNKNOWN, classify_risk


def round_average(value):
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Command(BaseCommand):
    help = "Recalculate stop risk within an existing completed analysis."

    def add_arguments(self, parser):
        parser.add_argument("analysis_id", type=int)

    @transaction.atomic
    def handle(self, *args, analysis_id, **options):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT parameters_json FROM analysis_run
                WHERE analysis_id = %s AND status = 'COMPLETED'
                FOR UPDATE
                """,
                [analysis_id],
            )
            row = cursor.fetchone()
        if row is None:
            raise CommandError(f"Completed analysis {analysis_id} does not exist.")
        try:
            parameters = json.loads(row[0])
        except ValueError as exc:
            raise CommandError("Analysis parameters contain invalid JSON.") from exc
        if not isinstance(parameters, dict):
            raise CommandError("Analysis parameters must be a JSON object.")

        analysis = AnalysisRun.objects.get(pk=analysis_id)
        route_counts = dict(
            RouteStop.objects.filter(pattern__network_id=analysis.network_id)
            .order_by()
            .values("stop_id")
            .annotate(route_count=Count("pattern__route_id", distinct=True))
            .values_list("stop_id", "route_count")
        )
        usage = {
            stop_id: (boarding, alighting, days)
            for stop_id, boarding, alighting, days in StopDailyUsage.objects.filter(
                batch_id=analysis.usage_batch_id,
                service_date__range=(analysis.period_start, analysis.period_end),
            )
            .values("stop_id")
            .annotate(
                boarding=Avg("boarding_count"),
                alighting=Avg("alighting_count"),
                days=Count("service_date"),
            )
            .values_list("stop_id", "boarding", "alighting", "days")
        }
        if not route_counts or not usage:
            raise CommandError("The analysis requires both route and usage data.")

        criteria = RiskCriteria()
        existing_stops = set(
            StopDiagnosis.objects.filter(analysis_id=analysis_id).values_list("stop_id", flat=True)
        )
        diagnoses = []
        for stop_id in sorted(route_counts.keys() | usage.keys() | existing_stops):
            route_count = route_counts.get(stop_id, 0)
            boarding, alighting, days = usage.get(stop_id, (None, None, 0))
            if days:
                level = classify_risk(route_count, boarding, criteria)
                boarding_text = f"일평균 승차 {round_average(boarding)}건"
            else:
                level = UNKNOWN
                boarding_text = "분석 기간에 승차 관측 자료 없음"
            diagnoses.append(
                StopDiagnosis(
                    analysis_id=analysis_id,
                    stop_id=stop_id,
                    risk_level=level,
                    risk_reason=f"경유 노선 {route_count}개 · {boarding_text}",
                    average_daily_boarding=round_average(boarding) if days else None,
                    average_daily_alighting=round_average(alighting) if days else None,
                    observed_days=days,
                    serving_route_count=route_count,
                    passengers_per_route=(
                        round_average(boarding / route_count) if days and route_count else None
                    ),
                    min_alternative_routes=max(route_count - 1, 0),
                )
            )

        StopDiagnosis.objects.bulk_create(
            diagnoses,
            batch_size=1000,
            update_conflicts=True,
            update_fields=[
                "risk_level", "risk_reason", "average_daily_boarding",
                "average_daily_alighting", "observed_days", "serving_route_count",
                "passengers_per_route", "min_alternative_routes",
            ],
        )
        parameters["criteria"] = criteria.as_dict()
        parameters["missing_boarding"] = UNKNOWN
        parameters["stop_risk_algorithm_version"] = "stop-risk-v1"
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE analysis_run SET parameters_json = %s WHERE analysis_id = %s",
                [json.dumps(parameters, ensure_ascii=False), analysis_id],
            )

        self.stdout.write(f"Updated {len(diagnoses)} stop diagnoses for analysis {analysis_id}.")
