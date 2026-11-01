"""Event bus: how live updates travel from whoever made a change to every browser.

    API request / worker  --publish-->  Redis channel "studyforge:study:{id}"
    every API instance    --subscribe-> forwards the event to its own WebSocket clients

Going through Redis (instead of calling the WebSocket hub directly) means:
  - the background worker, a separate process, can push job progress to browsers;
  - the API can run as several instances (e.g. Kubernetes pods) and every
    browser still gets every event, whichever pod it is connected to.

Tests and Redis-less local runs use InMemoryEventBus, which delivers directly.
"""

import asyncio
import json
import logging
from typing import Any, Protocol

from redis.asyncio import Redis

from app.realtime import hub

log = logging.getLogger(__name__)

CHANNEL_PREFIX = "studyforge:study:"


def channel_for(study_id: int) -> str:
    return f"{CHANNEL_PREFIX}{study_id}"


class EventBus(Protocol):
    async def publish(self, study_id: int, event: dict[str, Any]) -> None: ...


class InMemoryEventBus:
    """Single-process bus: delivers straight to this process's WebSocket clients."""

    async def publish(self, study_id: int, event: dict[str, Any]) -> None:
        await hub.broadcast(study_id, event)


class RedisEventBus:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def publish(self, study_id: int, event: dict[str, Any]) -> None:
        await self.redis.publish(channel_for(study_id), json.dumps(event, default=str))


async def forward_redis_events(redis: Redis) -> None:
    """Runs inside each API instance: Redis -> local WebSocket clients. Reconnects on errors."""
    while True:
        try:
            pubsub = redis.pubsub()
            await pubsub.psubscribe(f"{CHANNEL_PREFIX}*")
            async for message in pubsub.listen():
                if message.get("type") != "pmessage":
                    continue
                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()
                study_id = int(channel.removeprefix(CHANNEL_PREFIX))
                await hub.broadcast(study_id, json.loads(message["data"]))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Event forwarder lost its Redis connection; retrying in 2s")
            await asyncio.sleep(2)


# The bus the API uses. Replaced with a RedisEventBus at startup when Redis is reachable.
_bus: EventBus = InMemoryEventBus()


def get_bus() -> EventBus:
    return _bus


def set_bus(bus: EventBus) -> None:
    global _bus
    _bus = bus
