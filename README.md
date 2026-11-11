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
