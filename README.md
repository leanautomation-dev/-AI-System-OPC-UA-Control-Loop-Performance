# CLPM OPC-UA AI Monitoring System

Full-stack, production-grade control-loop performance monitoring platform connected live via OPC UA (IEC 62541), with AI anomaly detection, predictive alarms, TimescaleDB materialized views, and Apache Superset dashboards.

---

## Architecture

```
┌─────────────────┐     OPC UA     ┌──────────────────────────────────────────────────────────┐
│ PLC / DCS       │◄──────────────►│ asyncua OPC-UA Server (ns=2;s=PIC-001.PV …)              │
│ Purdue Level 1-2│    Port 4840   │   • 12 tags: PV / SP / CO × 4 controllers               │
└─────────────────┘                │   • Alarms & Events (condition-based)                     │
                                   └─────────────────┬────────────────────────────────────────┘
                                                      │ Subscription (1 Hz) + A&E handler
                                   ┌──────────────────▼────────────────────────────────────────┐
                                   │ asyncua OPC-UA Client  (opcua_client.py)                  │
                                   │   • Tag data-change handler → batch buffer → flush 2s     │
                                   │   • Alarm event handler → alarms stream                   │
                                   └────────┬──────────────────────────┬───────────────────────┘
                                            │ DB write (SQLAlchemy)     │ XADD (Redis Streams)
                                 ┌──────────▼──────────┐  ┌────────────▼────────────────────────┐
                                 │ TimescaleDB          │  │ Redis 7  (opcua:stream, opcua:alarms)│
                                 │   hypertables        │  └────────────────┬────────────────────┘
                                 │   6 continuous       │                   │ XREAD (blocking)
                                 │   aggregates (MV)    │  ┌────────────────▼────────────────────┐
                                 └──────────┬───────────┘  │ FastAPI  api_server.py  :8000        │
                                            │ REST          │   REST /api/v1/…                    │
                                            └──────────────►│   WS  /ws/tags  /ws/alarms  /ws/ai  │
                                                            │   AI engine (IsolationForest)       │
                                                            └──────┬──────────────┬───────────────┘
                                                                   │ :3000         │ :8088
                                                       ┌───────────▼────┐ ┌───────▼─────────────┐
                                                       │ React 18 + Vite│ │ Apache Superset 3.1  │
                                                       │  Dashboard     │ │  TimescaleDB source  │
                                                       │  Alarm Center  │ │  Embedded iframes    │
                                                       │  Controller    │ │  in CLPM.html        │
                                                       │  Analytics     │ └─────────────────────┘
                                                       └────────────────┘
```

---

## Quick Start (Docker Compose)

### Prerequisites
- Docker Desktop ≥ 24
- Docker Compose v2 (`docker compose`)

### 1 — Clone / copy `.env`

```bash
cd clpm-opcua-system
cp .env.example .env
# Edit .env if needed (defaults work out of the box)
```

### 2 — Start the stack

```bash
docker compose up -d
```

Services started (in dependency order):

| Service | Port | Description |
|---|---|---|
| `timescaledb` | 5432 | PostgreSQL + TimescaleDB |
| `redis` | 6379 | Redis Streams fan-out |
| `opcua-server` | 4840 | OPC-UA simulation server |
| `opcua-client` | — | Subscriber + DB writer |
| `csv-seed` | — | One-shot CSV → DB import |
| `api` | 8000 | FastAPI REST + WebSocket |
| `frontend` | 3000 | React Vite app (Nginx) |
| `superset` | 8088 | Apache Superset |
| `nginx` | 80 | Reverse proxy (all services) |

### 3 — Seed Superset

Superset init runs automatically via `superset-init` container. To re-run manually:

```bash
docker compose exec superset bash /app/docker/init_superset.sh
```

### 4 — Open dashboards & API docs

| URL | What |
|---|---|
| http://localhost | CLPM MonitoringStation (HTML entry-point) |
| http://localhost:3000 | React live OPC-UA dashboard |
| http://localhost:8088 | Apache Superset (admin / admin) |
| http://localhost:8000/docs | **FastAPI Swagger/OpenAPI documentation** for the backend API |
| http://localhost:8000/redoc | Alternative ReDoc API documentation interface |


### API endpoints

The FastAPI application exposes a simple REST/WS interface for clients and the
frontend. The OpenAPI schema is available at `/openapi.json` and the interactive
docs listed above include example requests. Key routes include:

- `GET  /api/v1/controllers` – list all controller IDs
- `GET  /api/v1/controllers/{id}/live` – latest PV/SP/CO values for a controller
- `GET  /api/v1/controllers/{id}/metrics` – historical CLPM metrics
- `GET  /api/v1/metrics` – performance metrics across all controllers
- `GET  /api/v1/tags/live` – all current tag values
- `GET  /api/v1/alarms` – active alarms
- `POST /api/v1/alarms/{id}/acknowledge` – acknowledge an alarm

WebSocket streams (JSON payloads) are exposed at:

- `/ws/tags` – tag updates at ~1 Hz
- `/ws/alarms` – alarm events
- `/ws/ai` – AI insight notifications

Clients can browse the swagger UI for request/response schemas, try out
parameters, and view autogenerated examples. For programmatic access simply
fetch the JSON OpenAPI spec and use any OpenAPI-compatible generator or client.

---

## Manual Development Setup

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Start each process in a separate terminal (the API server will provision the database schema on first run):

```bash
# 1 – OPC-UA simulation server
python opcua_server.py

# 2 – OPC-UA client (reads tags, writes DB, feeds Redis)
python opcua_client.py

# 3 – FastAPI API (will automatically provision the database schema if
#    the required tables don't yet exist)
uvicorn api_server:app --reload --port 8000
```

### Database (local TimescaleDB)

```bash
# assumes psql is installed and TimescaleDB extension available
psql -U postgres -c "CREATE DATABASE clpm_live;"
# apply schema and import CSV in one go (load_csv now runs schema.sql automatically)
psql -U postgres -d clpm_live -f db/schema.sql      # optional if you wish to run manually
python db/load_csv.py --csv ../clpm_metrics.csv     # script will also execute schema.sql before inserting
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev          # http://localhost:5173 (Vite dev)
npm run build        # production build → dist/
```

---

## Connecting to a Real PLC

The simulation OPC-UA server (`opcua_server.py`) is used by default.  
To connect to a **real PLC or DCS OPC-UA server**:

1. Set the environment variable in `.env`:
   ```
   OPCUA_REAL_ENDPOINT=opc.tcp://192.168.1.100:4840
   ```
2. Update `backend/config.yaml` → `opcua.tags` with the correct NodeIds for your PLC:
   ```yaml
   tags:
     - node_id: "ns=3;s=Site.Unit1.PIC001.PV"
       controller: PIC-001
       signal: PV
   ```
3. If the server requires authentication add:
   ```
   OPCUA_USER=opcuser
   OPCUA_PASS=secret
   ```
   and uncomment the credential lines in `opcua_client.py → connect()`.

---

## TimescaleDB Materialized Views

All CLPM aggregates are implemented as **TimescaleDB continuous aggregates** (auto-refreshing):

| View | Bucket | Refresh |
|---|---|---|
| `clpm_metrics_1min` | 1 minute | every 1 min |
| `clpm_metrics_hourly` | 1 hour | every 30 min |
| `clpm_metrics_daily` | 1 day | every 3 hr |
| `alarm_summary_hourly` | 1 hour | every 30 min |
| `clpm_imported_daily` | 1 day | every 3 hr |
| `ai_insights_daily` | 1 day | every 3 hr |

Query example:

```sql
SELECT bucket, controller, avg_aae, grade
FROM   clpm_metrics_hourly
WHERE  controller = 'PIC-001'
  AND  bucket > now() - INTERVAL '24 hours'
ORDER  BY bucket DESC;
```

---

## AI Engine

| Module | Algorithm | Purpose |
|---|---|---|
| `AnomalyDetector` | IsolationForest (window=60) | Multivariate anomaly detection on PV/SP/CO |
| `AlarmPredictor` | Linear regression on error trend | 15-min look-ahead predicted alarm |
| `compute_clpm_score` | IAE / AAE / pv_std / oscillation | 0-1 CLPM score + grade |

AI enriched data flows:
```
OPC-UA tags → AIManager.ingest() → ai_insights table → /ws/ai WebSocket → React Analytics page
```

---

## WebSocket API

Connect from any browser or script:

```js
// Live tag stream
const ws = new WebSocket('ws://localhost:8000/ws/tags');
ws.onmessage = (e) => {
  const { type, data } = JSON.parse(e.data);
  // type: "tag_batch" | "initial_snapshot"
  // data: [{ controller, signal, value, quality, ts }, ...]
};

// Alarm stream
const wsA = new WebSocket('ws://localhost:8000/ws/alarms');
// type: "alarm_snapshot" | "new_alarm"

// AI insights stream
const wsAI = new WebSocket('ws://localhost:8000/ws/ai');
// type: "ai_insights"
// data: [{ controller, anomaly_score, is_anomaly, predicted_alarm, clpm_score, grade, ... }]
```

---

## Project Structure

```
clpm-opcua-system/
├── backend/
│   ├── opcua_server.py      # Simulation OPC-UA server (asyncua)
│   ├── opcua_client.py      # OPC-UA subscriber + DB writer + A&E
│   ├── db_writer.py         # TimescaleDB async I/O (SQLAlchemy 2)
│   ├── redis_fanout.py      # Redis Streams publisher
│   ├── ai_engine.py         # Anomaly detection + CLPM scoring
│   ├── api_server.py        # FastAPI REST + WebSocket gateway
│   ├── config.yaml          # System config (tags, DB, Redis)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── db/
│       ├── schema.sql        # Hypertables + continuous aggregates
│       └── load_csv.py       # Seed clpm_metrics.csv into TimescaleDB
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── api/client.ts
│   │   ├── hooks/useOPCUAConnection.ts
│   │   ├── store/{tag,alarm,ai}Store.ts
│   │   ├── pages/{Dashboard,AlarmCenter,ControllerDetail,Analytics}.tsx
│   │   └── components/{ControlLoopCard,AlarmBanner,SystemKPIBar}.tsx
│   ├── Dockerfile
│   └── nginx.conf
├── superset/
│   ├── superset_config.py   # Embedded Superset + Redis cache
│   ├── init_superset.sh     # Auto-register TimescaleDB datasource
│   └── superset_queries.sql # Sample SQL for dashboards
├── nginx/
│   └── nginx.conf           # Reverse proxy (port 80)
├── docker-compose.yml
└── .env.example
```

---

## Environment Variables

See `.env.example` for the full list. Key variables:

| Variable | Default | Description |
|---|---|---|
| `OPCUA_REAL_ENDPOINT` | *(empty)* | Real PLC endpoint; if empty uses simulation server |
| `OPCUA_SERVER_URL` | `opc.tcp://opcua-server:4840/clpm/server/` | Internal OPC-UA URL |
| `DB_URL` | `postgresql+asyncpg://clpm:clpm@timescaledb/clpm_live` | TimescaleDB DSN |
| `REDIS_URL` | `redis://redis:6379` | Redis URL |
| `API_PORT` | `8000` | FastAPI port |
| `SUPERSET_SECRET_KEY` | `change-me-in-production` | Superset Flask secret |

### Lean Automation 2026 - NextGen Industrial Automation 