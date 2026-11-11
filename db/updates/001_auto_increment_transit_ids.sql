-- Preserve explicitly assigned IDs, including zero, while altering both keys.
SET @previous_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = CONCAT_WS(',', NULLIF(@previous_sql_mode, ''), 'NO_AUTO_VALUE_ON_ZERO');

-- MySQL requires session checks to be off to alter these referenced keys.
-- Both keys retain their type, index, and values.
SET @previous_foreign_key_checks = @@SESSION.foreign_key_checks;
SET SESSION foreign_key_checks = 0;

ALTER TABLE bus_stop
    MODIFY COLUMN stop_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '내부 정류소 ID';

ALTER TABLE bus_route
    MODIFY COLUMN route_id BIGINT NOT NULL AUTO_INCREMENT COMMENT '내부 노선 ID';

SET SESSION foreign_key_checks = @previous_foreign_key_checks;
SET SESSION sql_mode = @previous_sql_mode;
