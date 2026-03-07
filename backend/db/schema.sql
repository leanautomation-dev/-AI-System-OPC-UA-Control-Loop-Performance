-- ============================================================
-- CLPM OPC-UA  –  TimescaleDB Schema & Materialized Views
-- Apply with:  psql $DATABASE_URL -f schema.sql
-- ============================================================

-- ── Extensions ─────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ── Raw OPC-UA tag values ───────────────────────────────────
CREATE TABLE IF NOT EXISTS opcua_raw_tags (
    time            TIMESTAMPTZ     NOT NULL,
    node_id         TEXT            NOT NULL,
    controller      TEXT            NOT NULL,
    tag_type        TEXT            NOT NULL,          -- Pressure / Temperature / Flow / Level
    signal          TEXT            NOT NULL,          -- PV / SP / CO
    value           DOUBLE PRECISION,
    status          TEXT            DEFAULT 'Good'
);

SELECT create_hypertable(
    'opcua_raw_tags', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_tags_controller_time  ON opcua_raw_tags (controller, time DESC);
CREATE INDEX IF NOT EXISTS idx_tags_node_id_time     ON opcua_raw_tags (node_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_tags_signal           ON opcua_raw_tags (signal, time DESC);

-- Compression (keep 7 days uncompressed for live queries)
ALTER TABLE opcua_raw_tags SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'controller, signal'
);
SELECT add_compression_policy('opcua_raw_tags', INTERVAL '7 days', if_not_exists => TRUE);

-- Retention (keep 1 year of raw data)
SELECT add_retention_policy('opcua_raw_tags', INTERVAL '365 days', if_not_exists => TRUE);


-- ── OPC-UA Alarms & Events ──────────────────────────────────
CREATE TABLE IF NOT EXISTS opcua_alarms (
    id              BIGSERIAL,
    time            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    event_type      TEXT,
    source_name     TEXT,
    message         TEXT,
    severity        INTEGER         DEFAULT 0,   -- 0-1000 per OPC-UA spec
    acknowledged    BOOLEAN         DEFAULT FALSE,
    acknowledged_by TEXT,
    acknowledged_at TIMESTAMPTZ,
    resolved_at     TIMESTAMPTZ
);

SELECT create_hypertable(
    'opcua_alarms', 'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_alarms_ack  ON opcua_alarms (acknowledged, time DESC);
CREATE INDEX IF NOT EXISTS idx_alarms_sev  ON opcua_alarms (severity DESC, time DESC);


-- ── Imported CLPM metrics (from clpm_metrics.csv) ──────────
CREATE TABLE IF NOT EXISTS clpm_imported_metrics (
    time                TIMESTAMPTZ     NOT NULL,
    controller          TEXT            NOT NULL,
    controller_type     TEXT,
    recipe              TEXT,
    pv_mean             DOUBLE PRECISION,
    pv_std              DOUBLE PRECISION,
    pv_range            DOUBLE PRECISION,
    sp_mean             DOUBLE PRECISION,
    co_mean             DOUBLE PRECISION,
    co_std              DOUBLE PRECISION,
    aae                 DOUBLE PRECISION,
    iae                 DOUBLE PRECISION,
    co_travel           DOUBLE PRECISION,
    pct_auto            DOUBLE PRECISION,
    dominant_mode       TEXT,
    oscillation_index   INTEGER,
    n_samples           INTEGER
);

SELECT create_hypertable(
    'clpm_imported_metrics', 'time',
    chunk_time_interval => INTERVAL '30 days',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_clpm_ctrl_time ON clpm_imported_metrics (controller, time DESC);


-- ── AI Insights ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_insights (
    time                TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    controller          TEXT            NOT NULL,
    clpm_score          DOUBLE PRECISION,
    clpm_grade          TEXT,
    iae                 DOUBLE PRECISION,
    aae                 DOUBLE PRECISION,
    pv_std              DOUBLE PRECISION,
    co_travel           DOUBLE PRECISION,
    oscillation_index   INTEGER,
    is_anomaly          BOOLEAN         DEFAULT FALSE,
    anomaly_score       DOUBLE PRECISION,
    anomaly_reason      TEXT,
    predicted_alarm     BOOLEAN         DEFAULT FALSE,
    alarm_confidence    DOUBLE PRECISION,
    alarm_eta_minutes   INTEGER
);

SELECT create_hypertable(
    'ai_insights', 'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_ai_ctrl_time ON ai_insights (controller, time DESC);


-- ══════════════════════════════════════════════════════════════
-- CONTINUOUS AGGREGATES (Materialized Views via TimescaleDB)
-- ══════════════════════════════════════════════════════════════

-- ── 1-minute CLPM metrics from live OPC-UA tags ─────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS clpm_metrics_1min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 minute', time)       AS bucket,
    controller,
    tag_type,
    signal,
    AVG(value)                          AS avg_val,
    STDDEV(value)                       AS std_val,
    MIN(value)                          AS min_val,
    MAX(value)                          AS max_val,
    MAX(value) - MIN(value)             AS range_val,
    COUNT(*)                            AS n_samples,
    COUNT(*) FILTER (WHERE status != 'Good') AS bad_quality_count
FROM opcua_raw_tags
GROUP BY bucket, controller, tag_type, signal
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'clpm_metrics_1min',
    start_offset => INTERVAL '10 minutes',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists => TRUE
);


-- ── Hourly CLPM performance metrics ─────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS clpm_metrics_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time)         AS time,
    controller,
    tag_type,
    -- PV stats
    AVG(value)  FILTER (WHERE signal = 'PV')        AS pv_mean,
    STDDEV(value) FILTER (WHERE signal = 'PV')      AS pv_std,
    MAX(value)  FILTER (WHERE signal = 'PV')
      - MIN(value) FILTER (WHERE signal = 'PV')     AS pv_range,
    -- SP stats
    AVG(value)  FILTER (WHERE signal = 'SP')        AS sp_mean,
    -- CO stats
    AVG(value)  FILTER (WHERE signal = 'CO')        AS co_mean,
    STDDEV(value) FILTER (WHERE signal = 'CO')      AS co_std,
    -- Error-based KPIs  (approximated as AVG |PV-SP| from 1-min bucket data)
    COUNT(*)                                         AS n_samples,
    SUM(CASE WHEN status != 'Good' THEN 1 ELSE 0 END)::DOUBLE PRECISION
      / NULLIF(COUNT(*), 0)                          AS bad_quality_pct
FROM opcua_raw_tags
GROUP BY time_bucket('1 hour', time), controller, tag_type
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'clpm_metrics_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);


-- ── Daily CLPM summary ──────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS clpm_metrics_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time)          AS time,
    controller,
    tag_type,
    AVG(value)  FILTER (WHERE signal = 'PV')        AS pv_mean,
    STDDEV(value) FILTER (WHERE signal = 'PV')      AS pv_std,
    AVG(value)  FILTER (WHERE signal = 'SP')        AS sp_mean,
    AVG(value)  FILTER (WHERE signal = 'CO')        AS co_mean,
    COUNT(*)                                         AS n_samples
FROM opcua_raw_tags
GROUP BY time_bucket('1 day', time), controller, tag_type
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'clpm_metrics_daily',
    start_offset => INTERVAL '3 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '3 hours',
    if_not_exists => TRUE
);


-- ── Alarm aggregates ────────────────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS alarm_summary_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time)         AS bucket,
    source_name,
    COUNT(*)                            AS total_alarms,
    COUNT(*) FILTER (WHERE severity >= 900)  AS critical_count,
    COUNT(*) FILTER (WHERE severity >= 500 AND severity < 900) AS high_count,
    COUNT(*) FILTER (WHERE severity >= 200 AND severity < 500) AS medium_count,
    COUNT(*) FILTER (WHERE severity < 200)   AS low_count,
    COUNT(*) FILTER (WHERE acknowledged)     AS ack_count,
    AVG(severity)                            AS avg_severity
FROM opcua_alarms
GROUP BY time_bucket('1 hour', time), source_name
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'alarm_summary_hourly',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '30 minutes',
    if_not_exists => TRUE
);


-- ── Imported CLPM metrics – daily summary ───────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS clpm_imported_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time)          AS time,
    controller,
    controller_type,
    recipe,
    AVG(pv_mean)                        AS pv_mean_avg,
    AVG(pv_std)                         AS pv_std_avg,
    AVG(aae)                            AS aae_avg,
    AVG(iae)                            AS iae_avg,
    AVG(co_travel)                      AS co_travel_avg,
    AVG(pct_auto)                       AS pct_auto_avg,
    AVG(oscillation_index)              AS osc_index_avg,
    COUNT(*)                            AS n_records
FROM clpm_imported_metrics
GROUP BY time_bucket('1 day', time), controller, controller_type, recipe
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'clpm_imported_daily',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '6 hours',
    if_not_exists => TRUE
);


-- ── AI Insights – daily summary ─────────────────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS ai_insights_daily
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time)          AS time,
    controller,
    AVG(clpm_score)                     AS clpm_score_avg,
    MIN(clpm_score)                     AS clpm_score_min,
    COUNT(*) FILTER (WHERE is_anomaly)  AS anomaly_count,
    COUNT(*) FILTER (WHERE predicted_alarm) AS predicted_alarms,
    AVG(iae)                            AS iae_avg,
    AVG(oscillation_index)              AS osc_avg
FROM ai_insights
GROUP BY time_bucket('1 day', time), controller
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'ai_insights_daily',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '3 hours',
    if_not_exists => TRUE
);


-- ══════════════════════════════════════════════════════════════
-- HELPER VIEWS (for Superset dashboards)
-- ══════════════════════════════════════════════════════════════

-- Current live status per controller
CREATE OR REPLACE VIEW v_controller_status AS
SELECT DISTINCT ON (controller, signal)
    controller,
    tag_type,
    signal,
    value,
    status,
    time AS last_updated,
    CASE
        WHEN status != 'Good' THEN 'quality_bad'
        WHEN signal = 'PV' AND ABS(value - LAG(value) OVER (
            PARTITION BY controller, signal ORDER BY time
        )) / NULLIF(ABS(value), 0) > 0.15 THEN 'spike'
        ELSE 'normal'
    END AS state
FROM opcua_raw_tags
ORDER BY controller, signal, time DESC;


-- Alarm rate per controller (last 24h)
CREATE OR REPLACE VIEW v_alarm_rate_24h AS
SELECT
    source_name,
    COUNT(*) AS total_alarms,
    COUNT(*) FILTER (WHERE severity >= 900) AS critical,
    COUNT(*) FILTER (WHERE NOT acknowledged) AS active_unack,
    MAX(time) AS last_alarm_time
FROM opcua_alarms
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY source_name
ORDER BY total_alarms DESC;


-- CLPM performance band breakdown (from imported metrics)
CREATE OR REPLACE VIEW v_clpm_performance_bands AS
SELECT
    controller,
    controller_type,
    recipe,
    COUNT(*) AS total_hours,
    COUNT(*) FILTER (WHERE aae / NULLIF(sp_mean, 0) < 0.05)   AS good_pct_count,
    COUNT(*) FILTER (WHERE aae / NULLIF(sp_mean, 0) BETWEEN 0.05 AND 0.15) AS acceptable_count,
    COUNT(*) FILTER (WHERE aae / NULLIF(sp_mean, 0) > 0.15)   AS poor_count,
    AVG(pct_auto) AS avg_pct_auto,
    AVG(oscillation_index) AS avg_oscillation
FROM clpm_imported_metrics
GROUP BY controller, controller_type, recipe;


-- ── Seed imported CLPM data from CSV (run separately via Python) ──
-- See load_csv.py in this folder
