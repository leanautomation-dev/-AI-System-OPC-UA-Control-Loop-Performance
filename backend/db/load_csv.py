"""
Seed TimescaleDB with data from clpm_metrics.csv.
Usage:  python load_csv.py --csv ../../clpm_metrics.csv
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os

import pandas as pd
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
import yaml

log = logging.getLogger(__name__)

with open("../config.yaml") as f:
    CFG = yaml.safe_load(f)

DB_URL = CFG["database"]["url"].replace("postgresql://", "postgresql+asyncpg://")


async def load(csv_path: str):
    engine = create_async_engine(DB_URL, echo=False)

    # ensure the database schema is applied (runs schema.sql if not yet executed)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    async with engine.begin() as conn:
        try:
            with open(schema_path) as f:
                sql = f.read()
            # use exec_driver_sql to allow multiple statements
            await conn.exec_driver_sql(sql)
            log.info("Schema applied from %s", schema_path)
        except FileNotFoundError:
            log.warning("schema.sql not found, skipping schema creation")

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    df = df.rename(columns={"timestamp": "time"})
    df["time"] = pd.to_datetime(df["time"], utc=True)

    # Map CSV columns to DB columns
    col_map = {
        "time": "time",
        "controller": "controller",
        "controller_type": "controller_type",
        "recipe": "recipe",
        "pv_mean": "pv_mean",
        "pv_std": "pv_std",
        "pv_range": "pv_range",
        "sp_mean": "sp_mean",
        "co_mean": "co_mean",
        "co_std": "co_std",
        "aae": "aae",
        "iae": "iae",
        "co_travel": "co_travel",
        "pct_auto": "pct_auto",
        "dominant_mode": "dominant_mode",
        "oscillation_index": "oscillation_index",
        "n_samples": "n_samples",
    }
    df = df[[c for c in col_map if c in df.columns]]
    df.columns = [col_map[c] for c in df.columns]

    records = df.to_dict(orient="records")
    chunk_size = 1000

    async with engine.begin() as conn:
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            await conn.execute(
                text("""
                    INSERT INTO clpm_imported_metrics
                        (time, controller, controller_type, recipe,
                         pv_mean, pv_std, pv_range, sp_mean, co_mean, co_std,
                         aae, iae, co_travel, pct_auto, dominant_mode,
                         oscillation_index, n_samples)
                    VALUES
                        (:time, :controller, :controller_type, :recipe,
                         :pv_mean, :pv_std, :pv_range, :sp_mean, :co_mean, :co_std,
                         :aae, :iae, :co_travel, :pct_auto, :dominant_mode,
                         :oscillation_index, :n_samples)
                    ON CONFLICT DO NOTHING
                """),
                chunk,
            )
            log.info("Inserted rows %d – %d", i, i + len(chunk))

    log.info("CSV load complete. Total rows: %d", len(records))
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    p = argparse.ArgumentParser(description="Seed TimescaleDB with CLPM metrics CSV; applies schema.sql automatically.")
    p.add_argument("--csv", default="../../clpm_metrics.csv", help="path to metrics CSV file")
    args = p.parse_args()
    asyncio.run(load(args.csv))
