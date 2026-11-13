import json
from collections import defaultdict
from urllib.parse import urlencode
from urllib.request import urlopen

ENDPOINT = (
    "https://apis.data.go.kr/1613000/StopbyRouteTripVolume/"
    "getDailyStopbyRouteTripVolume"
)
DISTRICTS = ("41461", "41463", "41465")
PAGE_SIZE = 1000


class UsageUnavailable(ValueError):
    pass


def fetch_district(key, day, district, stations):
    """Collect all pages for a district before allowing them into a batch."""
    day_code = day.strftime("%Y%m%d")
    counts = defaultdict(lambda: [0, 0, None])
    api_ids = {}
    page, received, total = 1, 0, None
    seen = set()
    while total is None or received < total:
        params = urlencode(dict(
            serviceKey=key, pageNo=page, numOfRows=PAGE_SIZE, opr_ymd=day_code,
            ctpv_cd="41", sgg_cd=district, dataType="JSON",
        ))
        try:
            with urlopen(f"{ENDPOINT}?{params}", timeout=30) as response:
                payload = json.load(response)
                if payload.get("Error", {}).get("message") == "NO_DATA_FOUND":
                    raise UsageUnavailable("NO_DATA_FOUND")
                result = payload["Response"]
            if result["header"]["resultMsg"] != "SUCCESS":
                raise UsageUnavailable("이용량 API 오류")
            body = result["body"]
            page_total = int(body["totalCount"])
            total = page_total if total is None else total
            rows = body["items"]["item"]
            if isinstance(rows, dict):
                rows = [rows]
            if (
                total <= 0 or page_total != total or int(body["pageNo"]) != page
                or not isinstance(rows, list) or len(rows) != min(PAGE_SIZE, total - received)
            ):
                raise UsageUnavailable("이용량 API 페이지 불일치")
            for row in rows:
                if row["opr_ymd"] != day_code or str(row["sgg_cd"]) != district:
                    raise UsageUnavailable("응답 날짜 또는 지역 불일치")
                if row["trfc_mns_se_cd"] != "B":
                    continue
                row_key = tuple(row[field] for field in (
                    "sttn_id", "rte_id", "users_type_cd", "tzon",
                ))
                if row_key in seen:
                    raise UsageUnavailable("중복된 이용량 행")
                seen.add(row_key)
                identity = (str(row["sttn_ars_no"]), row["sttn_nm"].strip())
                stop_id = stations.get(identity)
                if stop_id is None:
                    continue
                api_id = str(row["sttn_id"])
                if api_ids.setdefault(stop_id, api_id) != api_id:
                    raise UsageUnavailable("API 정류장 ID가 중복 매핑됨")
                boarding, alighting = row["ride_nope"], row["goff_nope"]
                if any(type(n) is not int or n < 0 for n in (boarding, alighting)):
                    raise UsageUnavailable("승하차 건수 형식 불일치")
                counts[stop_id][0] += boarding
                counts[stop_id][1] += alighting
        except (AttributeError, KeyError, OSError, TypeError, ValueError) as error:
            if isinstance(error, UsageUnavailable):
                raise
            raise UsageUnavailable("API 연결 실패, 데이터 없음 또는 응답 형식 오류") from None
        received += len(rows)
        page += 1
    return counts
