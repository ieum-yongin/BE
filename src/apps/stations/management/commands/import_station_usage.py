import csv
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Avg, Count
from django.utils.timezone import now

from apps.alerts.models import AlertReview, UsageAlert
from apps.routes.models import RouteStop
from ieum_ai.simulation import UNKNOWN, RiskCriteria, classify_risk

from ...models import AnalysisRun, StopDailyUsage, StopDiagnosis
from ...usage_source import DISTRICTS, UsageUnavailable, fetch_district


class Command(BaseCommand):
    help = "국토부 승하차 API와 저장된 STCIS 배치로 새 이용량 배치를 만듭니다."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
        parser.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
        parser.add_argument("--batch-id", type=int, required=True)
        parser.add_argument("--fallback-batch-id", type=int, required=True)
        parser.add_argument("--fallback-csv", type=Path, required=True)
        parser.add_argument("--missing-csv", type=Path)
        parser.add_argument("--min-coverage", type=Decimal, default=Decimal("0.95"))
        parser.add_argument("--ai-dir", type=Path)
        parser.add_argument("--ai-python", default=sys.executable)
        parser.add_argument("--network-dir", type=Path)
        parser.add_argument("--network-id", type=int)
        parser.add_argument("--history-days", type=int, default=91)

    def handle(self, **options):
        start, end = options["start"], options["end"]
        batch_id, fallback_id = options["batch_id"], options["fallback_batch_id"]
        ai_dir, network_dir, network_id = (options[name] for name in ("ai_dir", "network_dir", "network_id"))
        if start > end or batch_id <= 0 or fallback_id <= 0 or batch_id == fallback_id:
            raise CommandError("기간 또는 배치 ID를 확인하세요.")
        if any((ai_dir, network_dir, network_id)) and not all((ai_dir, network_dir, network_id)):
            raise CommandError("--ai-dir, --network-dir, --network-id를 함께 지정하세요.")
        if options["history_days"] < 0:
            raise CommandError("--history-days는 0 이상이어야 합니다.")
        min_coverage = options["min_coverage"]
        if not min_coverage.is_finite() or not 0 < min_coverage <= 1:
            raise CommandError("--min-coverage는 0 초과 1 이하로 지정하세요.")
        key = os.getenv("STOP_BY_ROUTE_TRIP_VOLUME_SERVICE_KEY", "").strip()
        if not key:
            raise CommandError("STOP_BY_ROUTE_TRIP_VOLUME_SERVICE_KEY를 설정하세요.")

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT batch_id FROM data_batch WHERE batch_id = %s AND data_kind = 'USAGE' AND status = 'READY'",
                [fallback_id],
            )
            if cursor.fetchone() is None:
                raise CommandError("READY 상태의 STCIS 이용량 배치를 지정하세요.")
            cursor.execute("SELECT 1 FROM data_batch WHERE batch_id = %s", [batch_id])
            if cursor.fetchone():
                raise CommandError("새 배치 ID가 이미 존재합니다.")
            if network_id:
                cursor.execute("SELECT 1 FROM network_snapshot WHERE network_id = %s", [network_id])
                if cursor.fetchone() is None:
                    raise CommandError("분석에 사용할 노선망 ID가 존재하지 않습니다.")
            cursor.execute(
                "SELECT stop_id, source_stop_id, stop_number, name FROM bus_stop WHERE source_system = 'GBIS'"
            )
            stops = {stop: (source, ars, name) for stop, source, ars, name in cursor.fetchall()}

        identities = defaultdict(list)
        for stop, (_, ars, name) in stops.items():
            if ars and ars != "00000":
                identities[(ars, name.strip())].append(stop)
        stations = {identity: ids[0] for identity, ids in identities.items() if len(ids) == 1}

        history_start = start - timedelta(days=options["history_days"] if ai_dir else 0)
        stored = defaultdict(dict)
        for day, stop, board, alight, transfer in StopDailyUsage.objects.filter(
            batch_id=fallback_id, service_date__range=(history_start, end),
        ).values_list("service_date", "stop_id", "boarding_count", "alighting_count", "transfer_boarding_count"):
            if stop in stops:
                stored[day][stop] = (board, alight, transfer)

        source_ids = {source: stop for stop, (source, _, _) in stops.items()}
        expected, imputed = self.read_fallback_csv(options["fallback_csv"], source_ids, stored, start, end)
        missing = None
        if options["missing_csv"]:
            missing = defaultdict(set)
            try:
                with options["missing_csv"].open(encoding="utf-8-sig", newline="") as stream:
                    for row in csv.DictReader(stream):
                        if row["issue_type"] not in ("missing_day", "excluded_day"):
                            continue
                        day = date.fromisoformat(row["service_date"])
                        if not start <= day <= end:
                            continue
                        stop = source_ids[row["gbis_station_id"]]
                        if stop in stored.get(day, {}):
                            raise ValueError("미확보 대상이 이미 적재됨")
                        missing[day].add(stop)
            except (OSError, KeyError, TypeError, ValueError) as error:
                raise CommandError("미확보 검토 CSV와 DB 정류장을 대조하세요.") from error
            expected.update(stop for stops_on_day in missing.values() for stop in stops_on_day)
        usage = {}
        for offset in range((end - start).days + 1):
            day = start + timedelta(days=offset)
            saved = stored.get(day, {})
            targets = (
                missing.get(day, set()) if missing is not None
                else expected.difference(saved) | imputed.get(day, set())
            )
            remote = {}
            ambiguous = set()
            failed = []
            if targets:
                target_stations = {identity: stop for identity, stop in stations.items() if stop in targets}
                for district in DISTRICTS:
                    try:
                        district_usage = fetch_district(key, day, district, target_stations)
                    except UsageUnavailable as error:
                        failed.append(district)
                        self.stderr.write(f"{day} · {district} · {error}")
                        continue
                    ambiguous.update(remote.keys() & district_usage.keys())
                    remote.update(district_usage)
            for stop in ambiguous:
                remote.pop(stop)
            combined = saved | remote
            available = len(expected.intersection(combined))
            if available < len(expected) * min_coverage or (not saved and failed):
                raise CommandError(
                    f"{day} 적재 중단 · 대상 {len(expected)}곳 중 {available}곳 확보"
                    f" · 실패한 구 {len(failed)}곳"
                )
            usage[day] = combined
            replaced = imputed.get(day, set()) & remote.keys()
            verified_zero = sum(remote[stop][:2] == [0, 0] for stop in replaced)
            self.stdout.write(
                f"{day} · API {len(remote)}곳 · STCIS {len(combined) - len(remote)}곳"
                f" · 대체값 갱신 {len(replaced) - verified_zero}곳"
                f" · 확인된 0 {verified_zero}곳"
                f" · 미확인 대체 0 {len(imputed.get(day, set()) - replaced)}곳"
                f" · 대상 미확보 {len(expected) - available}곳"
            )

        with TemporaryDirectory(prefix="station-usage-") as folder:
            output = Path(folder)
            if ai_dir:
                input_path = output / "usage.csv"
                history = {day: rows for day, rows in stored.items() if day < start}
                with input_path.open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.writer(stream)
                    writer.writerow(("service_date", "source_stop_id", "stop_number", "stop_name",
                                     "boarding_count", "alighting_count", "transfer_boarding_count"))
                    for day, rows in sorted((history | usage).items()):
                        for stop, counts in rows.items():
                            writer.writerow((day, *stops[stop], *counts))
                env = os.environ.copy()
                env.pop("STOP_BY_ROUTE_TRIP_VOLUME_SERVICE_KEY", None)
                try:
                    subprocess.run([
                        options["ai_python"], str(ai_dir / "scripts" / "run_batch.py"),
                        "--data", str(input_path), "--from", str(start), "--to", str(end),
                        "--out", str(output), "--network-dir", str(network_dir),
                        "--stats-days", str((end - start).days + 1),
                    ], env=env, check=True)
                except (OSError, subprocess.CalledProcessError):
                    raise CommandError("AI 분석에 실패했습니다. 새 배치는 저장되지 않았습니다.") from None

            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO data_batch (batch_id, data_kind, source_name, source_reference,
                                               period_start, period_end, collected_at, status)
                       VALUES (%s, 'USAGE', 'StopbyRouteTripVolume / STCIS', %s, %s, %s, %s, 'READY')""",
                    [batch_id, f"STCIS fallback batch={fallback_id}", start, end, now()],
                )
                for day, rows in usage.items():
                    StopDailyUsage.objects.bulk_create([
                        StopDailyUsage(
                            batch_id=batch_id, stop_id=stop, service_date=day,
                            boarding_count=counts[0], alighting_count=counts[1],
                            transfer_boarding_count=counts[2],
                        )
                        for stop, counts in rows.items()
                    ], batch_size=1000)
                if ai_dir:
                    self.import_analysis(cursor, output, batch_id, network_id, start, end, stops, usage)

        self.stdout.write(self.style.SUCCESS(f"이용량 배치 {batch_id} 저장 완료"))

    def read_fallback_csv(self, path, source_ids, stored, start, end):
        expected = set()
        imputed = defaultdict(set)
        csv_rows = set()
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    stop = source_ids[row["gbis_station_id"]]
                    day = date.fromisoformat(row["service_date"])
                    flag = row["is_imputed"]
                    counts = (int(row["boarding_count"]), int(row["alighting_count"]))
                    if flag not in ("0", "1") or (flag == "1" and counts != (0, 0)):
                        raise ValueError("대체 행 형식 불일치")
                    expected.add(stop)
                    if not start <= day <= end:
                        continue
                    if (day, stop) in csv_rows or stored.get(day, {}).get(stop, ())[:2] != counts:
                        raise ValueError("CSV와 DB 이용량 배치 불일치")
                    csv_rows.add((day, stop))
                    if flag == "1":
                        imputed[day].add(stop)
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise CommandError("대체용 CSV와 STCIS 배치가 일치하는지 확인하세요.") from error
        db_rows = {(day, stop) for day, rows in stored.items() if start <= day <= end for stop in rows}
        if not expected or csv_rows != db_rows:
            raise CommandError("대체용 CSV의 대상 또는 날짜별 행이 STCIS 배치와 일치하지 않습니다.")
        return expected, imputed

    def import_analysis(self, cursor, output, batch_id, network_id, start, end, stops, usage):
        meta = json.loads((output / "analysis_run.json").read_text(encoding="utf-8"))
        if (meta["data_start"], meta["data_end"]) != (str(start), str(end)):
            raise CommandError("AI 분석 기간이 이용량 배치와 다릅니다.")
        ids = {fields[0]: stop for stop, fields in stops.items()}

        def rows(name):
            with (output / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
                records = list(csv.DictReader(stream))
            if len(records) != meta["counts"][name]:
                raise CommandError(f"{name} 결과 행 수가 다릅니다.")
            return records

        criteria = RiskCriteria()
        meta["config"]["criteria"] = criteria.as_dict()
        route_counts = dict(
            RouteStop.objects.filter(pattern__network_id=network_id).order_by().values("stop_id")
            .annotate(route_count=Count("pattern__route_id", distinct=True))
            .values_list("stop_id", "route_count")
        )
        if not route_counts:
            raise CommandError("선택한 노선망에 정류장 경유 정보가 없습니다.")
        cursor.execute(
            """INSERT INTO analysis_run (network_id, usage_batch_id, period_start, period_end,
                                         algorithm_version, parameters_json, status)
               VALUES (%s, %s, %s, %s, %s, %s, 'PENDING')""",
            [network_id, batch_id, start, end, meta["algorithm_version"], json.dumps(meta["config"])],
        )
        analysis_id = cursor.lastrowid
        diagnoses = rows("stop_diagnosis")
        if not diagnoses:
            raise CommandError("AI 정류장 진단 결과가 비어 있습니다.")
        transfers_unavailable = {
            stop for day_rows in usage.values() for stop, counts in day_rows.items()
            if counts[2] is None
        }
        cursor.executemany(
            """INSERT INTO stop_diagnosis (analysis_id, stop_id, risk_level, risk_reason,
                   average_daily_boarding, average_daily_alighting, observed_days,
                   city_boarding_rank, serving_route_count, passengers_per_route,
                   min_alternative_routes, transfer_ratio, stop_profile)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            [(analysis_id, ids[row["source_stop_id"]], row["risk_level"], row["risk_reason"] or None,
              row["average_daily_boarding"] or None, row["average_daily_alighting"] or None,
              row["observed_days"], row["city_boarding_rank"] or None, row["serving_route_count"] or None,
              row["passengers_per_route"] or None, row["min_alternative_routes"] or None,
              None if ids[row["source_stop_id"]] in transfers_unavailable else row["transfer_ratio"] or None,
              row["stop_profile"] or None) for row in diagnoses],
        )
        average_boardings = dict(
            StopDailyUsage.objects.filter(batch_id=batch_id).order_by().values("stop_id")
            .annotate(average=Avg("boarding_count")).values_list("stop_id", "average")
        )
        diagnosis_rows = list(StopDiagnosis.objects.filter(analysis_id=analysis_id))
        for diagnosis in diagnosis_rows:
            count = route_counts.get(diagnosis.stop_id, 0)
            board = average_boardings.get(diagnosis.stop_id)
            diagnosis.risk_level = classify_risk(count, board, criteria) if board is not None else UNKNOWN
            diagnosis.risk_reason = f"경유 노선 {count}개 · " + (
                f"일평균 승차 {board:.2f}건" if board is not None else "승차 관측 자료 없음"
            )
            diagnosis.serving_route_count = count
            diagnosis.passengers_per_route = board / count if board is not None and count else None
            diagnosis.min_alternative_routes = max(count - 1, 0)
        StopDiagnosis.objects.bulk_update(diagnosis_rows, [
            "risk_level", "risk_reason", "serving_route_count", "passengers_per_route",
            "min_alternative_routes",
        ], batch_size=1000)

        alerts = {}
        for row in rows("usage_alert"):
            stop_id = ids[row["source_stop_id"]]
            prior = UsageAlert.objects.filter(
                analysis__status="COMPLETED", station_id=stop_id,
                change_start=row["change_start"], change_direction=row["change_direction"],
            ).order_by("-analysis__completed_at", "-analysis_id", "-id").first()
            review_status = prior.review_status if prior else UsageAlert.ReviewStatus.NEW
            cursor.execute(
                """INSERT INTO usage_alert (analysis_id, stop_id, change_start, change_end, change_direction,
                       consecutive_days, baseline_daily_usage, observed_daily_usage, usage_ratio,
                       classification, expected_reason, review_status, analysis_summary)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [analysis_id, stop_id, row["change_start"], row["change_end"],
                 row["change_direction"], row["consecutive_days"], row["baseline_daily_usage"] or None,
                 row["observed_daily_usage"], row["usage_ratio"] or None, row["classification"],
                 row["expected_reason"] or None, review_status, row["analysis_summary"] or None],
            )
            alert_id = cursor.lastrowid
            alerts[row["alert_key"]] = alert_id
            if prior:
                AlertReview.objects.bulk_create([
                    AlertReview(alert_id=alert_id, status_after=status, note=note, created_at=created)
                    for status, note, created in AlertReview.objects.filter(alert_id=prior.pk)
                    .order_by("id").values_list("status_after", "note", "created_at")
                ], batch_size=1000)
        details = rows("alert_daily_detail")
        if details:
            cursor.executemany(
                """INSERT INTO alert_daily_detail (alert_id, service_date, baseline_usage, observed_usage, is_anomalous)
                   VALUES (%s,%s,%s,%s,%s)""",
                [(alerts[row["alert_key"]], row["service_date"], row["baseline_usage"] or None,
                  row["observed_usage"] or None, row["is_anomalous"].lower() == "true") for row in details],
            )
        AnalysisRun.objects.filter(pk=analysis_id).update(status="COMPLETED", completed_at=now())
