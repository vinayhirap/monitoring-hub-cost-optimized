# app/ws/pusher.py
from __future__ import annotations
import asyncio
import json
import logging

logger = logging.getLogger(__name__)
REDIS_URL = "redis://127.0.0.1:6379"
_stop = False


async def redis_listener():
    global _stop
    _stop = False

    while not _stop:
        r = None
        pubsub = None
        try:
            import redis.asyncio as aioredis
            from app.ws.manager import ws_manager

            r = aioredis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            pubsub = r.pubsub()
            await pubsub.subscribe(
                "channel:overview",
                "channel:alerts",
                "channel:metrics",
            )
            logger.info("Redis listener active")

            async for message in pubsub.listen():
                if _stop:
                    break
                if message["type"] != "message":
                    continue
                try:
                    channel = message["channel"].replace("channel:", "")
                    data    = json.loads(message["data"])
                    await ws_manager.broadcast(channel, data)
                except Exception as e:
                    logger.error(f"Redis message error: {e}")

        except asyncio.CancelledError:
            logger.info("Redis listener cancelled")
            break
        except Exception as e:
            if _stop:
                break
            logger.warning(f"Redis unavailable: {e} — retry in 10s")
        finally:
            # Suppress event loop closed errors during cleanup
            if pubsub:
                try:
                    await asyncio.wait_for(pubsub.unsubscribe(), timeout=2.0)
                except Exception:
                    pass
            if r:
                try:
                    await asyncio.wait_for(r.aclose(), timeout=2.0)
                except Exception:
                    pass

        if not _stop:
            await asyncio.sleep(2)


def stop_listener():
    global _stop
    _stop = True