-- ============================================================
-- LogScope – Apache Doris 4.x  OTel Native Schema
-- Exact schema as used by the official dorisexporter
-- (opentelemetry-collector-contrib dorisexporter component)
-- ============================================================

CREATE DATABASE IF NOT EXISTS otel;

USE otel;

-- ── otel_logs ─────────────────────────────────────────────────────────────────
-- Column layout matches the dorisexporter CREATE TABLE template verbatim.
--
-- Key design choices:
--   DUPLICATE KEY(timestamp, service_name)
--     → append-only log storage; every row is kept as-is.
--
--   PARTITION BY RANGE(timestamp) ()
--     → empty partition list: Doris auto-creates partitions dynamically
--       as data arrives (requires dynamic_partition properties below).
--
--   DISTRIBUTED BY RANDOM BUCKETS AUTO
--     → Doris chooses bucket count based on data volume; RANDOM avoids
--       hot-spots that HASH on a single column can create for log workloads.
--
--   body USING INVERTED PROPERTIES("parser"="unicode","support_phrase"="true")
--     → unicode tokeniser handles multi-language log lines and enables
--       phrase queries ("connection refused") in addition to MATCH_ANY.
--
--   resource_attributes / log_attributes USING INVERTED
--     → Doris 4.x can index VARIANT columns; allows filtering on nested
--       JSON fields such as resource_attributes["service.version"].

CREATE TABLE IF NOT EXISTS otel_logs
(
    timestamp             DATETIME(6),
    service_name          VARCHAR(200),
    service_instance_id   VARCHAR(200),
    trace_id              VARCHAR(200),
    span_id               STRING,
    severity_number       INT,
    severity_text         STRING,
    body                  STRING,
    resource_attributes   VARIANT,
    log_attributes        VARIANT,
    scope_name            STRING,
    scope_version         STRING,

    INDEX idx_service_name        (service_name)        USING INVERTED,
    INDEX idx_timestamp           (timestamp)           USING INVERTED,
    INDEX idx_service_instance_id (service_instance_id) USING INVERTED,
    INDEX idx_trace_id            (trace_id)            USING INVERTED,
    INDEX idx_span_id             (span_id)             USING INVERTED,
    INDEX idx_severity_number     (severity_number)     USING INVERTED,
    INDEX idx_body                (body)                USING INVERTED
          PROPERTIES("parser"="unicode", "support_phrase"="true"),
    INDEX idx_severity_text       (severity_text)       USING INVERTED,
    INDEX idx_resource_attributes (resource_attributes) USING INVERTED,
    INDEX idx_log_attributes      (log_attributes)      USING INVERTED,
    INDEX idx_scope_name          (scope_name)          USING INVERTED,
    INDEX idx_scope_version       (scope_version)       USING INVERTED
)
ENGINE = OLAP
DUPLICATE KEY(timestamp, service_name)
PARTITION BY RANGE(timestamp) ()
DISTRIBUTED BY RANDOM BUCKETS AUTO
PROPERTIES (
    "replication_num"                = "1",
    "inverted_index_storage_format"  = "V2",
    "compression"                    = "LZ4",

    -- Dynamic partition: Doris auto-creates one partition per day,
    -- keeps 7 days of future partitions, retains 30 days of history.
    "dynamic_partition.enable"       = "true",
    "dynamic_partition.time_unit"    = "DAY",
    "dynamic_partition.start"        = "-30",
    "dynamic_partition.end"          = "7",
    "dynamic_partition.prefix"       = "p",
    "dynamic_partition.buckets"      = "4"
);
