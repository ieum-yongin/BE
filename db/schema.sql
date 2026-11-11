-- MySQL 8.4 / 용용톤 이음 / Figma 디자인 반영
CREATE TABLE bus_company (
 company_id BIGINT NOT NULL COMMENT '운수회사 ID',
 name VARCHAR(100) NOT NULL COMMENT '운수회사명',
 PRIMARY KEY (company_id)
) COMMENT='운수회사';

CREATE TABLE data_batch (
 batch_id BIGINT NOT NULL COMMENT '수집 배치 ID',
 data_kind VARCHAR(20) NOT NULL COMMENT 'USAGE / NETWORK',
 source_name VARCHAR(200) NOT NULL COMMENT '원천 데이터명',
 source_reference VARCHAR(500) NULL COMMENT '원천 파일 또는 공개 API 참조',
 period_start DATE NOT NULL COMMENT '데이터 시작일',
 period_end DATE NOT NULL COMMENT '데이터 종료일',
 collected_at DATETIME NOT NULL COMMENT '수집 시각',
 status VARCHAR(20) NOT NULL COMMENT 'LOADING / READY / FAILED',
 PRIMARY KEY (batch_id)
) COMMENT='데이터 수집 이력';

CREATE TABLE bus_stop (
 stop_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '내부 정류소 ID',
 source_system VARCHAR(30) NOT NULL COMMENT '원천 시스템',
 source_stop_id VARCHAR(30) NOT NULL COMMENT '공공데이터 정류소 ID',
 stop_number VARCHAR(20) NULL COMMENT '표시 정류소 번호',
 name VARCHAR(200) NOT NULL COMMENT '정류소명',
 latitude DECIMAL(10,7) NOT NULL COMMENT '위도',
 longitude DECIMAL(10,7) NOT NULL COMMENT '경도',
 district_name VARCHAR(50) NULL COMMENT '구',
 neighborhood_name VARCHAR(50) NULL COMMENT '동',
 direction_label VARCHAR(120) NULL COMMENT '정류소가 향하는 방면 표시명',
 road_address VARCHAR(255) NULL COMMENT '정류소 도로명 주소',
 PRIMARY KEY (stop_id),
 UNIQUE (source_system, source_stop_id)
) COMMENT='정류소';

CREATE TABLE bus_route (
 route_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '내부 노선 ID',
 operator_id BIGINT NOT NULL COMMENT '운수회사 기관 ID',
 source_system VARCHAR(30) NOT NULL COMMENT '원천 시스템',
 source_route_id VARCHAR(30) NOT NULL COMMENT '공공데이터 노선 ID',
 route_number VARCHAR(30) NOT NULL COMMENT '노선 번호',
 route_type VARCHAR(30) NOT NULL COMMENT '시내 / 마을 / 광역 등',
 PRIMARY KEY (route_id),
 UNIQUE (source_system, source_route_id)
) COMMENT='버스 노선';

CREATE TABLE network_snapshot (
 network_id BIGINT NOT NULL COMMENT '노선망 버전 ID',
 source_batch_id BIGINT NOT NULL COMMENT '노선 데이터 배치 ID',
 name VARCHAR(100) NOT NULL COMMENT '버전명',
 effective_date DATE NOT NULL COMMENT '기준일',
 created_at DATETIME NOT NULL COMMENT '생성 시각',
 PRIMARY KEY (network_id)
) COMMENT='노선망 스냅샷';

CREATE TABLE route_pattern (
 pattern_id BIGINT NOT NULL COMMENT '방향별 운행경로 ID',
 network_id BIGINT NOT NULL COMMENT '노선망 버전 ID',
 route_id BIGINT NOT NULL COMMENT '노선 ID',
 pattern_code VARCHAR(40) NOT NULL COMMENT '상하행 및 분기 경로 코드',
 direction_name VARCHAR(100) NOT NULL COMMENT '운행 방향명',
 first_departure TIME NULL COMMENT '첫차',
 last_departure TIME NULL COMMENT '막차',
 headway_minutes SMALLINT NULL COMMENT '배차 간격 분',
 PRIMARY KEY (pattern_id),
 UNIQUE (network_id, route_id, pattern_code)
) COMMENT='버전별 노선 운행경로';

CREATE TABLE route_stop (
 pattern_id BIGINT NOT NULL COMMENT '운행경로 ID',
 stop_sequence INT NOT NULL COMMENT '경유 순번',
 stop_id BIGINT NOT NULL COMMENT '정류소 ID',
 distance_from_start_m DECIMAL(10,2) NULL COMMENT '기점부터 누적 거리 m',
 PRIMARY KEY (pattern_id, stop_sequence)
) COMMENT='노선 경유 정류소';

CREATE TABLE stop_daily_usage (
 batch_id BIGINT NOT NULL COMMENT '이용량 데이터 배치 ID',
 stop_id BIGINT NOT NULL COMMENT '정류소 ID',
 service_date DATE NOT NULL COMMENT '이용 일자',
 boarding_count INT NOT NULL COMMENT '하루 승차 건수',
 alighting_count INT NOT NULL COMMENT '하루 하차 건수',
 transfer_boarding_count INT NULL COMMENT '환승 승차 건수 미제공 시 NULL',
 PRIMARY KEY (batch_id, stop_id, service_date)
) COMMENT='정류소 일별 이용량';

CREATE TABLE analysis_run (
 analysis_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '분석 실행 ID',
 network_id BIGINT NOT NULL COMMENT '분석 노선망 버전 ID',
 usage_batch_id BIGINT NOT NULL COMMENT '분석 이용량 배치 ID',
 period_start DATE NOT NULL COMMENT '조회 분석 시작일',
 period_end DATE NOT NULL COMMENT '조회 분석 종료일',
 algorithm_version VARCHAR(50) NOT NULL COMMENT '진단 알고리즘 버전',
 parameters_json TEXT NOT NULL COMMENT '위험도 및 급변 기준 등 JSON',
 status VARCHAR(20) NOT NULL COMMENT 'PENDING / RUNNING / COMPLETED / FAILED',
 completed_at DATETIME NULL COMMENT '분석 완료 시각',
 PRIMARY KEY (analysis_id)
) COMMENT='분석 실행 및 기준';

CREATE TABLE stop_diagnosis (
 analysis_id BIGINT NOT NULL COMMENT '분석 실행 ID',
 stop_id BIGINT NOT NULL COMMENT '정류소 ID',
 risk_level VARCHAR(20) NOT NULL COMMENT 'SAFE / CAUTION / DANGER / UNKNOWN',
 risk_reason VARCHAR(500) NULL COMMENT '등급 판정 근거',
 average_daily_boarding DECIMAL(12,2) NULL COMMENT '유효 관측일 평균 승차',
 average_daily_alighting DECIMAL(12,2) NULL COMMENT '유효 관측일 평균 하차',
 observed_days INT NOT NULL COMMENT '실제 관측일 수',
 city_boarding_rank INT NULL COMMENT '용인시 승차 순위',
 serving_route_count INT NULL COMMENT '중복 방향 제외 경유 노선 수',
 passengers_per_route DECIMAL(12,2) NULL COMMENT '노선당 평균 이용량',
 min_alternative_routes INT NULL COMMENT '단일 노선 중단 시 최소 대체 노선',
 transfer_ratio DECIMAL(7,4) NULL COMMENT '환승 승차 비율 0~1',
 stop_profile VARCHAR(30) NULL COMMENT '출발형 / 도착형 / 균형형',
 PRIMARY KEY (analysis_id, stop_id)
) COMMENT='정류소 위험도 및 요약';

CREATE TABLE route_overlap (
 analysis_id BIGINT NOT NULL COMMENT '분석 실행 ID',
 pattern_a_id BIGINT NOT NULL COMMENT '비교 운행경로 A ID',
 pattern_b_id BIGINT NOT NULL COMMENT '비교 운행경로 B ID',
 shared_segment_count INT NOT NULL COMMENT '동일 방향 공통 인접 구간 수',
 shared_distance_m DECIMAL(12,2) NULL COMMENT '공통 구간 거리 m',
 overlap_ratio_a DECIMAL(7,4) NOT NULL COMMENT 'A 경로 대비 중복률 0~1',
 overlap_ratio_b DECIMAL(7,4) NOT NULL COMMENT 'B 경로 대비 중복률 0~1',
 shared_stop_count INT NULL COMMENT '두 운행경로의 서로 다른 공통 정류소 수',
 PRIMARY KEY (analysis_id, pattern_a_id, pattern_b_id)
) COMMENT='노선 중복 진단';

CREATE TABLE major_hub (
 hub_id BIGINT NOT NULL COMMENT '거점 ID',
 name VARCHAR(100) NOT NULL COMMENT '시청 또는 역 등 거점명',
 latitude DECIMAL(10,7) NOT NULL COMMENT '거점 위도',
 longitude DECIMAL(10,7) NOT NULL COMMENT '거점 경도',
 PRIMARY KEY (hub_id)
) COMMENT='주요 거점';

CREATE TABLE hub_stop (
 hub_id BIGINT NOT NULL COMMENT '거점 ID',
 stop_id BIGINT NOT NULL COMMENT '거점 접근 정류소 ID',
 walk_distance_m INT NULL COMMENT '거점까지 도보 거리 m',
 PRIMARY KEY (hub_id, stop_id)
) COMMENT='거점 연결 정류소';

CREATE TABLE stop_hub_access (
 analysis_id BIGINT NOT NULL COMMENT '분석 실행 ID',
 stop_id BIGINT NOT NULL COMMENT '출발 정류소 ID',
 hub_id BIGINT NOT NULL COMMENT '목적 거점 ID',
 direct_route_count INT NOT NULL COMMENT '직행 노선 수',
 minimum_transfers SMALLINT NULL COMMENT '최소 환승 횟수 도달불가 시 NULL',
 is_reachable BOOLEAN NOT NULL COMMENT '거점 도달 가능 여부',
 PRIMARY KEY (analysis_id, stop_id, hub_id)
) COMMENT='정류소 거점 접근성';

CREATE TABLE stop_hub_direct_route (
 analysis_id BIGINT NOT NULL COMMENT '분석 실행 ID',
 stop_id BIGINT NOT NULL COMMENT '출발 정류소 ID',
 hub_id BIGINT NOT NULL COMMENT '목적 거점 ID',
 route_id BIGINT NOT NULL COMMENT '환승 없이 목적 거점에 연결하는 노선 ID',
 PRIMARY KEY (analysis_id, stop_id, hub_id, route_id)
) COMMENT='거점별 직행 노선';

CREATE TABLE usage_alert (
 alert_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '급변 알림 ID',
 analysis_id BIGINT NOT NULL COMMENT '분석 실행 ID',
 stop_id BIGINT NOT NULL COMMENT '정류소 ID',
 change_start DATE NOT NULL COMMENT '변화 시작일',
 change_end DATE NOT NULL COMMENT '변화 종료일',
 change_direction VARCHAR(10) NOT NULL COMMENT 'INCREASE / DECREASE',
 consecutive_days INT NOT NULL COMMENT '연속 변화 일수',
 baseline_daily_usage DECIMAL(12,2) NULL COMMENT '동일 요일 기준 평소 승하차',
 observed_daily_usage DECIMAL(12,2) NOT NULL COMMENT '변화기간 평균 승하차',
 usage_ratio DECIMAL(9,4) NULL COMMENT '평소 대비 배수',
 classification VARCHAR(20) NOT NULL COMMENT 'NEEDS_CHECK / EXPECTED',
 expected_reason VARCHAR(200) NULL COMMENT '방학 또는 학사일정 등',
 review_status VARCHAR(20) NOT NULL COMMENT 'NEW / REVIEWING / RESOLVED',
 analysis_summary TEXT NULL COMMENT '사용 추이 분석 결과의 화면 표시용 요약',
 PRIMARY KEY (alert_id)
) COMMENT='이용 급변 알림';

CREATE TABLE alert_daily_detail (
 alert_id BIGINT NOT NULL COMMENT '급변 알림 ID',
 service_date DATE NOT NULL COMMENT '그래프 일자',
 baseline_usage DECIMAL(12,2) NULL COMMENT '해당 요일 평소 이용량',
 observed_usage INT NULL COMMENT '당일 실제 이용량 미수집 시 NULL',
 is_anomalous BOOLEAN NOT NULL COMMENT '급변 구간 해당 여부',
 PRIMARY KEY (alert_id, service_date)
) COMMENT='급변 알림 일별 근거';

CREATE TABLE alert_review (
 review_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '검토 이력 ID',
 alert_id BIGINT NOT NULL COMMENT '급변 알림 ID',
 note TEXT NULL COMMENT '원인 메모',
 status_after VARCHAR(20) NOT NULL COMMENT '검토 후 상태',
 created_at DATETIME NOT NULL COMMENT '검토 시각',
 PRIMARY KEY (review_id)
) COMMENT='알림 검토 및 원인 메모';

CREATE TABLE simulation (
 simulation_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '시뮬레이션 ID',
 baseline_analysis_id BIGINT NOT NULL COMMENT '변경 전 분석 실행 ID',
 title VARCHAR(200) NOT NULL COMMENT '저장할 시뮬레이션명',
 status VARCHAR(20) NOT NULL COMMENT 'DRAFT / RUNNING / COMPLETED / FAILED',
 parameters_json TEXT NOT NULL COMMENT '영향인원 추정법 등 JSON',
 created_at DATETIME NOT NULL COMMENT '생성 시각',
 completed_at DATETIME NULL COMMENT '계산 완료 시각',
 PRIMARY KEY (simulation_id)
) COMMENT='만약에 시뮬레이션';

CREATE TABLE simulation_route_change (
 simulation_id BIGINT NOT NULL COMMENT '시뮬레이션 ID',
 route_id BIGINT NOT NULL COMMENT '운행 중단 노선 ID 전체 방향 적용',
 change_type VARCHAR(20) NOT NULL COMMENT 'SUSPEND',
 PRIMARY KEY (simulation_id, route_id)
) COMMENT='시뮬레이션 중단 노선';

CREATE TABLE simulation_stop_result (
 simulation_id BIGINT NOT NULL COMMENT '시뮬레이션 ID',
 stop_id BIGINT NOT NULL COMMENT '정류소 ID',
 after_risk_level VARCHAR(20) NOT NULL COMMENT '변경 후 신호등 등급',
 remaining_route_count INT NOT NULL COMMENT '중단 후 남은 노선 수',
 after_min_alternatives INT NULL COMMENT '변경 후 최소 대체 노선 수',
 estimated_affected_daily DECIMAL(12,2) NULL COMMENT '추정 일별 영향 승하차 건수',
 is_isolated BOOLEAN NOT NULL COMMENT '운행 노선이 없어 고립되는지',
 reason VARCHAR(500) NULL COMMENT '등급 변화 또는 고립 근거',
 PRIMARY KEY (simulation_id, stop_id)
) COMMENT='시뮬레이션 정류소별 결과';

ALTER TABLE bus_route ADD CONSTRAINT fk_route_operator FOREIGN KEY (operator_id) REFERENCES bus_company (company_id);
ALTER TABLE network_snapshot ADD CONSTRAINT fk_network_batch FOREIGN KEY (source_batch_id) REFERENCES data_batch (batch_id);
ALTER TABLE route_pattern ADD CONSTRAINT fk_pattern_network FOREIGN KEY (network_id) REFERENCES network_snapshot (network_id);
ALTER TABLE route_pattern ADD CONSTRAINT fk_pattern_route FOREIGN KEY (route_id) REFERENCES bus_route (route_id);
ALTER TABLE route_stop ADD CONSTRAINT fk_route_stop_pattern FOREIGN KEY (pattern_id) REFERENCES route_pattern (pattern_id);
ALTER TABLE route_stop ADD CONSTRAINT fk_route_stop_stop FOREIGN KEY (stop_id) REFERENCES bus_stop (stop_id);
ALTER TABLE stop_daily_usage ADD CONSTRAINT fk_daily_batch FOREIGN KEY (batch_id) REFERENCES data_batch (batch_id);
ALTER TABLE stop_daily_usage ADD CONSTRAINT fk_daily_stop FOREIGN KEY (stop_id) REFERENCES bus_stop (stop_id);
ALTER TABLE analysis_run ADD CONSTRAINT fk_analysis_network FOREIGN KEY (network_id) REFERENCES network_snapshot (network_id);
ALTER TABLE analysis_run ADD CONSTRAINT fk_analysis_usage FOREIGN KEY (usage_batch_id) REFERENCES data_batch (batch_id);
ALTER TABLE stop_diagnosis ADD CONSTRAINT fk_diagnosis_analysis FOREIGN KEY (analysis_id) REFERENCES analysis_run (analysis_id);
ALTER TABLE stop_diagnosis ADD CONSTRAINT fk_diagnosis_stop FOREIGN KEY (stop_id) REFERENCES bus_stop (stop_id);
ALTER TABLE route_overlap ADD CONSTRAINT fk_overlap_analysis FOREIGN KEY (analysis_id) REFERENCES analysis_run (analysis_id);
ALTER TABLE route_overlap ADD CONSTRAINT fk_overlap_a FOREIGN KEY (pattern_a_id) REFERENCES route_pattern (pattern_id);
ALTER TABLE route_overlap ADD CONSTRAINT fk_overlap_b FOREIGN KEY (pattern_b_id) REFERENCES route_pattern (pattern_id);
ALTER TABLE hub_stop ADD CONSTRAINT fk_hub_stop_hub FOREIGN KEY (hub_id) REFERENCES major_hub (hub_id);
ALTER TABLE hub_stop ADD CONSTRAINT fk_hub_stop_stop FOREIGN KEY (stop_id) REFERENCES bus_stop (stop_id);
ALTER TABLE stop_hub_access ADD CONSTRAINT fk_access_diagnosis FOREIGN KEY (analysis_id, stop_id) REFERENCES stop_diagnosis (analysis_id, stop_id);
ALTER TABLE stop_hub_access ADD CONSTRAINT fk_access_hub FOREIGN KEY (hub_id) REFERENCES major_hub (hub_id);
ALTER TABLE stop_hub_direct_route ADD CONSTRAINT fk_direct_route_access FOREIGN KEY (analysis_id, stop_id, hub_id) REFERENCES stop_hub_access (analysis_id, stop_id, hub_id);
ALTER TABLE stop_hub_direct_route ADD CONSTRAINT fk_direct_route_route FOREIGN KEY (route_id) REFERENCES bus_route (route_id);
ALTER TABLE usage_alert ADD CONSTRAINT fk_alert_diagnosis FOREIGN KEY (analysis_id, stop_id) REFERENCES stop_diagnosis (analysis_id, stop_id);
ALTER TABLE alert_daily_detail ADD CONSTRAINT fk_alert_daily_alert FOREIGN KEY (alert_id) REFERENCES usage_alert (alert_id);
ALTER TABLE alert_review ADD CONSTRAINT fk_review_alert FOREIGN KEY (alert_id) REFERENCES usage_alert (alert_id);
ALTER TABLE simulation ADD CONSTRAINT fk_simulation_analysis FOREIGN KEY (baseline_analysis_id) REFERENCES analysis_run (analysis_id);
ALTER TABLE simulation_route_change ADD CONSTRAINT fk_sim_route_simulation FOREIGN KEY (simulation_id) REFERENCES simulation (simulation_id);
ALTER TABLE simulation_route_change ADD CONSTRAINT fk_sim_route_route FOREIGN KEY (route_id) REFERENCES bus_route (route_id);
ALTER TABLE simulation_stop_result ADD CONSTRAINT fk_sim_result_simulation FOREIGN KEY (simulation_id) REFERENCES simulation (simulation_id);
ALTER TABLE simulation_stop_result ADD CONSTRAINT fk_sim_result_stop FOREIGN KEY (stop_id) REFERENCES bus_stop (stop_id);
