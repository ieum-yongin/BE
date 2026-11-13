# BE

## 로컬 MySQL 초기화

`.env.example`을 `.env`로 복사하고 `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`MYSQL_ROOT_PASSWORD`를 설정합니다.

```bash
docker compose up -d --build
docker compose exec web python src/manage.py migrate
```

호스트에서 3306 포트를 이미 사용 중이면 `.env`의 `DB_PORT`를 3307 같은 빈 포트로 바꿉니다. Django 컨테이너는 내부 주소 `db:3306`으로 접속합니다.

새 MySQL 볼륨을 처음 시작하면 `db/schema.sql`에 정의된 서비스 테이블이 생성됩니다.
기존 볼륨에서 서비스 테이블이 아직 하나도 없다면 다음 명령으로 스키마를 적용할 수 있습니다.

```bash
docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql --default-character-set=utf8mb4 -u "$MYSQL_USER" "$MYSQL_DATABASE"' < db/schema.sql
```

기존 볼륨에 서비스 테이블이 이미 있다면 아래 SQL을 실행해 정류소와 노선의 내부 ID에 자동 증가를 적용합니다.

```bash
docker compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_PASSWORD" mysql --default-character-set=utf8mb4 -u "$MYSQL_USER" "$MYSQL_DATABASE"' < db/updates/001_auto_increment_transit_ids.sql
```

### 국토부 승하차 이용량 배치와 AI 분석

서버 실행 환경에 `STOP_BY_ROUTE_TRIP_VOLUME_SERVICE_KEY`를 주입한 뒤 실행합니다.

```bash
python src/manage.py import_station_usage \
  --from 2026-10-04 --to 2026-10-31 \
  --batch-id NEW_BATCH_ID --fallback-batch-id STCIS_BATCH_ID \
  --fallback-csv /path/to/stop_daily_usage_ready.csv \
  --ai-dir /path/to/AI --ai-python /path/to/AI/.venv/bin/python \
  --network-dir /path/to/network-csv --network-id NETWORK_ID
```

배치 ID와 노선망 ID는 실제 숫자로 바꿉니다. 대체 배치는 READY 상태인 STCIS
승하차 배치이며, 적재에 사용한 원본 CSV로 0 대체 행을 식별합니다.
기존 관측 행은 유지합니다. 0 대체 행과 미확보 정류장은 API에서 ARS 번호와
정류장명으로 대조합니다. API에서 확인된 수치를 저장하고, 확인하지 못한 대체값은
기존 0을 유지합니다. 한 구에서 페이지 조회가 실패해도 다른 구의 결과는 사용합니다.
날짜별로 원본 CSV 대상 정류장의 95%를 확보해야 저장합니다. 필요하면
`--min-coverage`로 기준을 설정할 수 있습니다. STCIS 행이 없는 날짜는 세 구의
API 페이지 조회가 모두 완료되어야 합니다.

미확보 검토 CSV를 `--missing-csv /path/to/stop_daily_usage_review.csv`로 지정하면
해당 CSV의 미확보 날짜·정류장만 보완하고 기존 0 대체값도 그대로 유지합니다.

AI 저장소, 실행 환경, 모델 및 노선 CSV는 실행 환경에서 접근 가능해야 합니다.
AI 분석에는 대체 배치에서 확보할 수 있는 직전 91일의 이력도 전달합니다.
`--history-days`로 이력 범위를 조정할 수 있습니다. 분석 결과가 모두 저장된 후에
완료 분석으로 전환되며, 이용량·지도·알림·시뮬레이션의 기준이 새 분석으로 갱신됩니다.
AI 관련 세 옵션을 생략하면 이용량 배치만 저장합니다.
