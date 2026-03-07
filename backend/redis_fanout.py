"""
Redis Fanout  –  Publishes tag data and alarm events to Redis Streams
so the WebSocket API server can push to all connected browsers.
"""
from __future__ import annotations
import json
import logging
from typing import Any

import redis.asyncio as aioredis
import yaml

log = logging.getLogger(__name__)

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

REDIS_URL = CFG["redis"]["url"]
STREAM_KEY = CFG["redis"]["stream_key"]
ALARM_STREAM_KEY = CFG["redis"]["alarm_stream_key"]
MAX_LEN = CFG["redis"]["max_len"]


class RedisFanout:
    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def init(self):
        self._redis = await aioredis.from_url(REDIS_URL, decode_responses=True)
        log.info("Redis connected: %s", REDIS_URL)

    async def publish_batch(self, records: list[dict]):
        if not self._redis or not records:
            return
        pipe = self._redis.pipeline()
        for record in records:
            fields = {k: str(v) for k, v in record.items()}
            pipe.xadd(STREAM_KEY, fields, maxlen=MAX_LEN, approximate=True)
        await pipe.execute()

    async def publish_alarm(self, record: dict):
        if not self._redis:
            return
        fields = {k: str(v) for k, v in record.items()}
        await self._redis.xadd(
            ALARM_STREAM_KEY, fields, maxlen=MAX_LEN, approximate=True
        )

    async def get_latest_tag(self, controller: str, signal: str) -> dict | None:
        if not self._redis:
            return None
        entries = await self._redis.xrevrange(STREAM_KEY, count=100)
        for _, fields in entries:
            if (
                fields.get("controller") == controller
                and fields.get("signal") == signal
            ):
                return fields
        return None
