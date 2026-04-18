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

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path) as f:
    CFG = yaml.safe_load(f)

# Use environment variable directly (set in docker-compose.yml)
# For debugging, hardcode the URL
DB_URL = "postgresql+asyncpg://streampipes:streampipes@timescaledb:5432/streampipes"


async def load(csv_path: str):
    engine = create_async_engine(DB_URL, echo=False)

    # ensure the database schema is applied (runs schema.sql if not yet executed)
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    async with engine.begin() as conn:
        try:
            # Check if schema is already applied
            result = await conn.execute(text("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'opcua_raw_tags')"))
            schema_exists = result.fetchone()[0]
            
            if not schema_exists:
                # Use raw connection to execute multiple statements
                raw_conn = await engine.raw_connection()
                try:
                    cursor = await raw_conn.cursor()
                    with open(schema_path) as f:
                        sql_content = f.read()
                    await cursor.execute(sql_content)
                    await raw_conn.commit()
                    log.info("Schema applied from %s", schema_path)
                finally:
                    await raw_conn.close()
            else:
                log.info("Schema already exists, skipping schema application")
        except FileNotFoundError:
            log.warning("schema.sql not found, skipping schema creation")

    df = pd.read_csv(csv_path, parse_dates=[0])
    df = df.rename(columns={df.columns[0]: "time"})
    df["time"] = pd.to_datetime(df["time"], utc=True)

    # Transform wide format CSV to long format for opcua_raw_tags table
    # CSV columns are like: "PIC-002.MODE (2D402F04-9434-4840-9861-E24E87BD4F03)"
    records = []
    for _, row in df.iterrows():
        timestamp = row["time"]
        for col_name, value in row.items():
            if col_name == "time":
                continue
            if pd.isna(value):
                continue
                
            # Parse column name: "CONTROLLER.SIGNAL (NODE_ID)"
            if " (" in col_name and col_name.endswith(")"):
                tag_part = col_name[:col_name.rfind(" (")]
                node_id = col_name[col_name.rfind(" (")+2:-1]
                
                if "." in tag_part:
                    controller, signal = tag_part.split(".", 1)
                    
                    # Map signal to tag_type
                    tag_type_map = {
                        "PV": "Pressure",  # Default, would need more logic for actual mapping
                        "SP": "Pressure",
                        "CO": "Pressure", 
                        "MODE": "Mode"
                    }
                    tag_type = tag_type_map.get(signal, "Unknown")
                    
                    record = {
                        "time": timestamp,
                        "node_id": node_id,
                        "controller": controller,
                        "tag_type": tag_type,
                        "signal": signal,
                        "value": float(value) if isinstance(value, (int, float)) and not pd.isna(value) else None,
                        "status": "Good"
                    }
                    
                    # Only add records with required fields
                    if controller and signal and node_id:
                        records.append(record)

    log.info(f"Transformed {len(records)} records from CSV data")
    if records:
        log.info(f"Sample record: {records[0]}")

    chunk_size = 1000

    async with engine.begin() as conn:
        for i in range(0, len(records), chunk_size):
            chunk = records[i : i + chunk_size]
            await conn.execute(
                text("""
                    INSERT INTO opcua_raw_tags
                        (time, node_id, controller, tag_type, signal, value, status)
                    VALUES
                        (:time, :node_id, :controller, :tag_type, :signal, :value, :status)
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
