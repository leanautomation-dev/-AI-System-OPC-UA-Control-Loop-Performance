-- ──────────────────────────────────────────────────────────────
-- Superset SQL Lab  –  example queries for CLPM dashboards
-- These become Saved Queries / Virtual Datasets in Superset.
-- ──────────────────────────────────────────────────────────────

-- ① Hourly CLPM Fleet Performance (for line chart)
-- Dataset name: clpm_fleet_hourly_perf
SELECT
    time,
    controller,
    pv_mean,
    sp_mean,
    co_mean,
    pv_std,
    n_samples,
    ROUND((1.0 - LEAST(ABS(pv_mean - sp_mean) / NULLIF(ABS(sp_mean), 0), 1.0))::NUMERIC, 4) AS clpm_score
FROM clpm_metrics_hourly
WHERE time > NOW() - INTERVAL '7 days'
ORDER BY controller, time;


-- ② Controller grade overview (for pie / donut chart)
-- Dataset name: clpm_grade_overview
SELECT
    controller,
    ROUND(AVG(
        (1.0 - LEAST(ABS(pv_mean - sp_mean) / NULLIF(ABS(sp_mean), 0), 1.0))
    )::NUMERIC, 4) AS avg_clpm_score,
    CASE
        WHEN AVG((1.0 - LEAST(ABS(pv_mean - sp_mean) / NULLIF(ABS(sp_mean), 0), 1.0))) >= 0.85 THEN 'Good'
        WHEN AVG((1.0 - LEAST(ABS(pv_mean - sp_mean) / NULLIF(ABS(sp_mean), 0), 1.0))) >= 0.70 THEN 'Acceptable'
        WHEN AVG((1.0 - LEAST(ABS(pv_mean - sp_mean) / NULLIF(ABS(sp_mean), 0), 1.0))) >= 0.40 THEN 'Poor'
        ELSE 'Bad'
    END AS grade
FROM clpm_metrics_hourly
WHERE time > NOW() - INTERVAL '24 hours'
GROUP BY controller;


-- ③ Alarm rate heatmap (source × hour)
-- Dataset name: alarm_heatmap
SELECT
    bucket,
    source_name,
    total_alarms,
    critical_count,
    high_count,
    avg_severity
FROM alarm_summary_hourly
WHERE bucket > NOW() - INTERVAL '7 days'
ORDER BY bucket DESC, total_alarms DESC;


-- ④ IAE trend from imported CSV data
-- Dataset name: iae_trend_imported
SELECT
    time,
    controller,
    controller_type,
    recipe,
    iae,
    aae,
    pv_std,
    oscillation_index,
    pct_auto
FROM clpm_imported_metrics
WHERE time > NOW() - INTERVAL '30 days'
ORDER BY controller, time;


-- ⑤ AI anomaly summary
-- Dataset name: ai_anomaly_daily
SELECT
    time,
    controller,
    clpm_score_avg,
    clpm_score_min,
    anomaly_count,
    predicted_alarms,
    iae_avg,
    osc_avg
FROM ai_insights_daily
ORDER BY time DESC, controller;


-- ⑥ CLPM performance bands (from imported data)
-- Dataset name: clpm_performance_bands
SELECT * FROM v_clpm_performance_bands;


-- ⑦ Live controller status
-- Dataset name: controller_live_status
SELECT * FROM v_controller_status;


-- ⑧ 24-hour alarm rate
-- Dataset name: alarm_rate_24h
SELECT * FROM v_alarm_rate_24h;
