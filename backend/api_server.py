"""
FastAPI API Server  –  REST + WebSocket gateway
Provides:
  GET  /api/v1/controllers              – list all controllers
  GET  /api/v1/controllers/{id}/live    – latest PV/SP/CO values
  GET  /api/v1/controllers/{id}/metrics – historical CLPM metrics
  GET  /api/v1/alarms                   – active alarms
  POST /api/v1/alarms/{id}/acknowledge  – ack alarm
  GET  /api/v1/tags/live                – all latest tag values
  WS   /ws/tags                         – live tag stream (1 Hz)
  WS   /ws/alarms                       – live alarm stream
  WS   /ws/ai                           – AI insight stream
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

import redis.asyncio as aioredis
from config import load_config
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_engine import ai_manager
from db_writer import DBWriter
from redis_fanout import RedisFanout

log = logging.getLogger(__name__)

# use central loader to expand environment variables
CFG = load_config()

API_CFG = CFG["api"]
REDIS_CFG = CFG["redis"]

# ─────────────────────────────────────────────────────────────────────────────
# Shared resources
# ─────────────────────────────────────────────────────────────────────────────
db = DBWriter()
fanout = RedisFanout()
_redis: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis
    # initialise database connection & ensure schema exists
    await db.init()

    # verify core tables are present; if not, reprovision
    try:
        await db.get_controllers()
    except Exception as exc:
        # common missing-table error from asyncpg translates to ProgrammingError
        log.warning("initial controller query failed, attempting schema provision: %s", exc)
        try:
            await db.provision()
        except Exception as exc2:  # pragma: no cover - should be rare
            log.error("schema provision failed: %s", exc2)
            raise

    await fanout.init()
    _redis = await aioredis.from_url(CFG["redis"]["url"], decode_responses=True)
    log.info("API server ready.")
    yield
    if _redis:
        await _redis.aclose()


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CLPM OPC-UA AI API",
    version="1.0.0",
    description="Real-time Control Loop Performance Monitoring via OPC-UA",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CFG["cors_origins"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# REST endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/v1/controllers", tags=["Controllers"])
async def list_controllers():
    controllers = await db.get_controllers()
    return {"controllers": controllers}


@app.get("/api/v1/tags/live", tags=["Tags"])
async def get_all_live_tags():
    values = await db.get_latest_values()
    return {"tags": values, "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/api/v1/controllers/{controller_id}/live", tags=["Controllers"])
async def get_controller_live(controller_id: str):
    all_vals = await db.get_latest_values()
    ctrl_vals = [v for v in all_vals if v["controller"] == controller_id]
    if not ctrl_vals:
        raise HTTPException(status_code=404, detail="Controller not found")
    by_signal = {v["signal"]: v for v in ctrl_vals}
    return {
        "controller": controller_id,
        "signals": by_signal,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/controllers/{controller_id}/metrics", tags=["Controllers"])
async def get_controller_metrics(controller_id: str, hours: int = 24):
    metrics = await db.get_clpm_metrics(controller=controller_id, hours=hours)
    return {"controller": controller_id, "metrics": metrics}


@app.get("/api/v1/metrics", tags=["Metrics"])
async def get_all_metrics(hours: int = 24):
    metrics = await db.get_clpm_metrics(hours=hours)
    return {"metrics": metrics}


@app.get("/api/v1/alarms", tags=["Alarms"])
async def get_active_alarms():
    alarms = await db.get_active_alarms()
    return {"alarms": alarms, "count": len(alarms)}


@app.post("/api/v1/alarms/{alarm_id}/acknowledge", tags=["Alarms"])
async def acknowledge_alarm(alarm_id: int, user: str = "operator"):
    await db.acknowledge_alarm(alarm_id, user)
    return {"status": "acknowledged", "alarm_id": alarm_id}


@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket helpers
# ─────────────────────────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws) if hasattr(self.active, "discard") else None
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


tag_manager = ConnectionManager()
alarm_manager = ConnectionManager()
ai_manager_ws = ConnectionManager()


async def redis_stream_to_ws(
    manager: ConnectionManager,
    stream_key: str,
    transform_fn=None,
):
    """Read from a Redis Stream and broadcast to all WS clients."""
    last_id = "$"
    while True:
        try:
            results = await _redis.xread(
                {stream_key: last_id}, block=1000, count=50
            )
            if results:
                for _, entries in results:
                    batch = []
                    for entry_id, fields in entries:
                        last_id = entry_id
                        item = dict(fields)
                        if transform_fn:
                            item = transform_fn(item)
                        batch.append(item)
                    if batch and manager.active:
                        await manager.broadcast(json.dumps({"data": batch}))
        except Exception as exc:
            log.error("Redis stream error: %s", exc)
            await asyncio.sleep(1)


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.websocket("/ws/tags")
async def ws_tags(websocket: WebSocket):
    await tag_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        tag_manager.disconnect(websocket)


@app.websocket("/ws/alarms")
async def ws_alarms(websocket: WebSocket):
    await alarm_manager.connect(websocket)
    try:
        # Send current active alarms on connect
        alarms = await db.get_active_alarms()
        await websocket.send_text(
            json.dumps({"type": "snapshot", "data": alarms})
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        alarm_manager.disconnect(websocket)


@app.websocket("/ws/ai")
async def ws_ai(websocket: WebSocket):
    await ai_manager_ws.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ai_manager_ws.disconnect(websocket)


# ─────────────────────────────────────────────────────────────────────────────
# Background broadcaster tasks
# ─────────────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(
        redis_stream_to_ws(tag_manager, REDIS_CFG["stream_key"])
    )
    asyncio.create_task(
        redis_stream_to_ws(alarm_manager, REDIS_CFG["alarm_stream_key"])
    )
    asyncio.create_task(_ai_broadcast_loop())


async def _ai_broadcast_loop():
    """Every second, pull latest tags, run AI, broadcast insights."""
    while True:
        await asyncio.sleep(1.0)
        if not ai_manager_ws.active:
            continue
        latest = await db.get_latest_values()
        insights = ai_manager.ingest(latest)
        if insights:
            await ai_manager_ws.broadcast(
                json.dumps({"type": "ai_insights", "data": insights})
            )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host=API_CFG["host"], port=API_CFG["port"])
