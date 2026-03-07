"""
CLPM OPC-UA Client  –  Subscribes to the server (simulation or real PLC),
writes data into TimescaleDB, and fans out live updates over Redis Streams.
"""
from __future__ import annotations
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import yaml
from asyncua import Client, Node, ua

from db_writer import DBWriter
from redis_fanout import RedisFanout

log = logging.getLogger(__name__)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

OPCUA_CFG = CFG["opcua"]
TAGS: list[dict] = OPCUA_CFG["tags"]


# ─────────────────────────────────────────────────────────────────────────────
# Subscription handler
# ─────────────────────────────────────────────────────────────────────────────
class TagDataChangeHandler:
    def __init__(self, db: DBWriter, fanout: RedisFanout, tag_map: dict):
        self.db = db
        self.fanout = fanout
        self.tag_map = tag_map  # monitoredItemId -> tag dict
        self._buffer: list[dict] = []
        self._flush_lock = asyncio.Lock()

    def datachange_notification(self, node: Node, val: Any, data: Any):
        """Called by asyncua on each value change (from thread-pool)."""
        item_id = data.monitored_item.Value.ClientHandle
        tag = self.tag_map.get(item_id)
        if not tag:
            return
        ts = data.monitored_item.Value.SourceTimestamp or datetime.now(timezone.utc)
        record = {
            "timestamp": ts.isoformat(),
            "node_id": tag["node_id"],
            "controller": tag["controller"],
            "type": tag["type"],
            "signal": tag["node_id"].split(".")[-1],
            "value": float(val) if val is not None else None,
            "status": "Good",
        }
        self._buffer.append(record)

    def event_notification(self, event: ua.EventData):
        pass  # Handled by AlarmsEventHandler


class AlarmsEventHandler:
    def __init__(self, db: DBWriter, fanout: RedisFanout):
        self.db = db
        self.fanout = fanout

    def event_notification(self, event: ua.EventData):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": str(event.EventType),
            "source_name": str(getattr(event, "SourceName", "")),
            "message": str(getattr(event, "Message", "")),
            "severity": int(getattr(event, "Severity", 0)),
            "acknowledged": False,
        }
        asyncio.create_task(self._persist(record))

    async def _persist(self, record: dict):
        await self.db.insert_alarm(record)
        await self.fanout.publish_alarm(record)


# ─────────────────────────────────────────────────────────────────────────────
# Main client
# ─────────────────────────────────────────────────────────────────────────────
class CLPMOpcuaClient:
    def __init__(self):
        self.db = DBWriter()
        self.fanout = RedisFanout()
        self.client = Client(OPCUA_CFG["client"]["endpoint"])
        self._tag_map: dict[int, dict] = {}
        self._subscription = None
        self._ae_subscription = None
        self._handler: TagDataChangeHandler | None = None
        self._flush_interval = 2.0  # seconds

    async def connect(self):
        await self.db.init()
        await self.fanout.init()
        await self.client.connect()
        log.info(
            "Connected to OPC-UA server: %s", OPCUA_CFG["client"]["endpoint"]
        )
        ns_idx = await self.client.get_namespace_index(
            OPCUA_CFG["server"]["namespace"]
        )
        self._handler = TagDataChangeHandler(self.db, self.fanout, self._tag_map)
        self._subscription = await self.client.create_subscription(
            OPCUA_CFG["client"]["subscription_interval"], self._handler
        )

        nodes_to_subscribe = []
        for tag in TAGS:
            try:
                node = self.client.get_node(ua.NodeId(tag["node_id"], ns_idx))
                nodes_to_subscribe.append(node)
            except Exception as exc:
                log.warning("Tag %s not found: %s", tag["node_id"], exc)

        results = await self._subscription.subscribe_data_change(
            nodes_to_subscribe,
        )
        for i, (tag, handle) in enumerate(zip(TAGS, results)):
            self._tag_map[handle] = tag

        # Subscribe to Alarm & Events
        ae_handler = AlarmsEventHandler(self.db, self.fanout)
        self._ae_subscription = await self.client.create_subscription(
            200, ae_handler
        )
        server_node = self.client.get_node(ua.ObjectIds.Server)
        await self._ae_subscription.subscribe_events(server_node)

        log.info("Subscribed to %d tags + A&E events.", len(nodes_to_subscribe))

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(self._flush_interval)
            if self._handler and self._handler._buffer:
                async with self._handler._flush_lock:
                    batch = self._handler._buffer.copy()
                    self._handler._buffer.clear()
                await self.db.insert_tag_batch(batch)
                await self.fanout.publish_batch(batch)

    async def run(self):
        await self.connect()
        try:
            await self._flush_loop()
        finally:
            if self._subscription:
                await self._subscription.delete()
            if self._ae_subscription:
                await self._ae_subscription.delete()
            await self.client.disconnect()
            log.info("OPC-UA client disconnected.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(CLPMOpcuaClient().run())
