"""
DB Writer  –  All TimescaleDB interactions live here.
Chunks are auto-created by TimescaleDB for time-series tables.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from config import load_config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

log = logging.getLogger(__name__)

# load_config handles `${VAR:default}` interpolation using environment
# variables.  previously this module read the YAML directly, so any
# `${DATABASE_URL:…}` placeholder would remain unexpanded, resulting in
# SQLAlchemy errors at startup.
CFG = load_config()

DB_URL = CFG["database"]["url"].replace("postgresql://", "postgresql+asyncpg://")


class DBWriter:
    def __init__(self):
        self._engine = None
        self._session_factory = None

    async def init(self):
        self._engine = create_async_engine(
            DB_URL,
            pool_size=CFG["database"]["pool_size"],
            max_overflow=CFG["database"]["max_overflow"],
            pool_timeout=CFG["database"]["pool_timeout"],
            echo=False,
        )
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        log.info("DB engine initialised.")

        # apply schema on startup if file exists
        schema_path = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
        if os.path.isfile(schema_path):
            with open(schema_path) as f:
                sql = f.read()
            # exec_driver_sql may only run the first statement; split on semicolons
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                try:
                    # open a fresh connection for each statement to avoid
                    # discarded transaction state lingering
                    conn2 = await self._engine.connect()
                    try:
                        await conn2.exec_driver_sql(stmt)
                    finally:
                        await conn2.close()
                except Exception as exc:  # pragma: no cover - log and continue
                    log.warning("schema statement failed (%s): %s", stmt[:100], exc)
            log.info("Database schema applied from %s", schema_path)
        else:
            log.warning("schema.sql not found at %s, skipping schema provision", schema_path)

    async def _session(self) -> AsyncSession:
        return self._session_factory()

    async def provision(self) -> None:
        """Re-run the schema file against the current database connection.

        Can be used by callers that detect missing tables and want to create
        them without restarting the entire service.
        """
        schema_path = os.path.join(os.path.dirname(__file__), "db", "schema.sql")
        if not os.path.isfile(schema_path):
            log.warning("provision called but schema.sql not found at %s", schema_path)
            return
        with open(schema_path) as f:
            sql = f.read()
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                conn2 = await self._engine.connect()
                try:
                    await conn2.exec_driver_sql(stmt)
                finally:
                    await conn2.close()
            except Exception as exc:
                log.warning("provision stmt failed (%s): %s", stmt[:100], exc)
        log.info("Database schema provisioned via provision()")

    async def insert_tag_batch(self, records: list[dict]):
        if not records:
            return
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO opcua_raw_tags
                        (time, node_id, controller, tag_type, signal, value, status)
                    VALUES
                        (:timestamp, :node_id, :controller, :type, :signal, :value, :status)
                    ON CONFLICT DO NOTHING
                """),
                records,
            )
            await session.commit()

    async def insert_alarm(self, record: dict):
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    INSERT INTO opcua_alarms
                        (time, event_type, source_name, message, severity, acknowledged)
                    VALUES
                        (:timestamp, :event_type, :source_name, :message, :severity, :acknowledged)
                """),
                record,
            )
            await session.commit()

    async def get_controllers(self) -> list[str]:
        async with self._session_factory() as session:
            result = await session.execute(
                text("SELECT DISTINCT controller FROM opcua_raw_tags ORDER BY controller")
            )
            return [row[0] for row in result.fetchall()]

    async def get_latest_values(self) -> list[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT DISTINCT ON (controller, signal)
                        controller, signal, value, status, time
                    FROM opcua_raw_tags
                    ORDER BY controller, signal, time DESC
                """)
            )
            rows = result.mappings().all()
            return [dict(r) for r in rows]

    async def get_clpm_metrics(
        self,
        controller: str | None = None,
        hours: int = 24,
    ) -> list[dict]:
        where = "WHERE time > NOW() - INTERVAL :interval"
        params: dict = {"interval": f"{hours} hours"}
        if controller:
            where += " AND controller = :controller"
            params["controller"] = controller
        async with self._session_factory() as session:
            result = await session.execute(
                text(f"""
                    SELECT *
                    FROM clpm_metrics_hourly
                    {where}
                    ORDER BY controller, time
                """),
                params,
            )
            return [dict(r) for r in result.mappings().all()]

    async def get_active_alarms(self) -> list[dict]:
        async with self._session_factory() as session:
            result = await session.execute(
                text("""
                    SELECT * FROM opcua_alarms
                    WHERE acknowledged = FALSE
                    ORDER BY time DESC
                    LIMIT 200
                """)
            )
            return [dict(r) for r in result.mappings().all()]

    async def acknowledge_alarm(self, alarm_id: int, user: str):
        async with self._session_factory() as session:
            await session.execute(
                text("""
                    UPDATE opcua_alarms
                    SET acknowledged = TRUE,
                        acknowledged_by = :user,
                        acknowledged_at = NOW()
                    WHERE id = :alarm_id
                """),
                {"alarm_id": alarm_id, "user": user},
            )
            await session.commit()
