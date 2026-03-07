#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# init_superset.sh  –  Bootstrap Superset with CLPM data source & dashboards.
# Run once after `docker compose up -d superset`.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SUPERSET_URL="${SUPERSET_URL:-http://localhost:8088}"
ADMIN_USER="${SUPERSET_ADMIN:-admin}"
ADMIN_PASS="${SUPERSET_PASSWORD:-admin}"
DB_URL="${DATABASE_URL:-postgresql://streampipes:streampipes@timescaledb:5432/streampipes}"

echo "⏳ Waiting for Superset to be ready…"
until curl -sf "${SUPERSET_URL}/health" > /dev/null; do sleep 3; done

echo "🔑 Obtaining access token…"
TOKEN=$(curl -sf -X POST "${SUPERSET_URL}/api/v1/security/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\",\"provider\":\"db\",\"refresh\":true}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

AUTH="-H \"Authorization: Bearer ${TOKEN}\""

# ── Register TimescaleDB data source ────────────────────────────────────────
echo "📡 Registering TimescaleDB data source…"
curl -sf -X POST "${SUPERSET_URL}/api/v1/database/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"database_name\": \"CLPM TimescaleDB\",
    \"sqlalchemy_uri\": \"${DB_URL}\",
    \"expose_in_sqllab\": true,
    \"allow_multi_schema_metadata_fetch\": true,
    \"allow_ctas\": true,
    \"allow_cvas\": true,
    \"allow_run_async\": true,
    \"extra\": \"{\\\"metadata_params\\\":{},\\\"engine_params\\\":{}}\"
  }" | python3 -c "import sys,json; d=json.load(sys.stdin); print('DB ID:', d.get('id',d))"

# ── Register datasets (materialized views) ───────────────────────────────────
echo "📊 Registering datasets…"

for TABLE in clpm_metrics_hourly clpm_metrics_daily alarm_summary_hourly \
             v_controller_status v_alarm_rate_24h v_clpm_performance_bands \
             clpm_imported_daily ai_insights_daily; do
  curl -sf -X POST "${SUPERSET_URL}/api/v1/dataset/" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"database\": 1,
      \"schema\": \"public\",
      \"table_name\": \"${TABLE}\"
    }" > /dev/null && echo "  ✓ ${TABLE}" || echo "  ⚠ ${TABLE} (may already exist)"
done

# ── Import dashboard bundle if present ──────────────────────────────────────
DASH_ZIP="${BASH_SOURCE%/*}/dashboards/clpm_dashboard.zip"
if [[ -f "${DASH_ZIP}" ]]; then
  echo "📦 Importing CLPM dashboard bundle…"
  curl -sf -X POST "${SUPERSET_URL}/api/v1/dashboard/import/" \
    -H "Authorization: Bearer ${TOKEN}" \
    -F "formData=@${DASH_ZIP}" \
    -F "passwords={}" > /dev/null && echo "  ✓ Dashboard imported."
else
  echo "ℹ Dashboard bundle not found – create dashboards manually in Superset."
fi

echo ""
echo "✅ Superset initialised. Open: ${SUPERSET_URL}"
echo "   User: ${ADMIN_USER} / ${ADMIN_PASS}"
