"""
Railway MCP Server Keep-Alive Service

Prevents Railway from sleeping by pinging the health endpoint every 5 minutes.
This eliminates 60-90s cold start delays on first request.

Usage:
    from kai.services.railway_keepalive import start_keepalive

    # In your FastAPI startup:
    @app.on_event("startup")
    async def startup():
        start_keepalive()
"""

import asyncio
import httpx
import logging
import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Railway MCP server URL
RAILWAY_URL = os.getenv("DEPTH_ESTIMATION_URL") or os.getenv("MIDAS_MCP_URL")
PING_INTERVAL = 300  # 5 minutes (Railway sleeps after 10 min inactivity)


async def ping_railway() -> bool:
    """
    Ping Railway MCP server health endpoint.

    Returns:
        True if ping successful, False otherwise
    """
    if not RAILWAY_URL:
        logger.warning("⚠️ Railway URL not configured, skipping ping")
        return False

    try:
        health_url = f"{RAILWAY_URL.rstrip('/')}/health"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url)

            if response.status_code == 200:
                logger.debug(f"💚 Railway keepalive: {health_url} is warm")
                return True
            else:
                logger.warning(f"⚠️ Railway keepalive: {health_url} returned {response.status_code}")
                return False

    except httpx.RequestError as e:
        logger.warning(f"⚠️ Railway keepalive failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Railway keepalive error: {e}")
        return False


async def keepalive_loop():
    """Background task that pings Railway every 5 minutes"""
    logger.info(f"🔥 Railway keepalive service started (ping every {PING_INTERVAL}s)")

    # Initial ping on startup
    await ping_railway()

    while True:
        try:
            await asyncio.sleep(PING_INTERVAL)
            await ping_railway()
        except asyncio.CancelledError:
            logger.info("🛑 Railway keepalive service stopped")
            break
        except Exception as e:
            logger.error(f"❌ Railway keepalive loop error: {e}")
            # Continue loop even if error occurs
            await asyncio.sleep(PING_INTERVAL)


# Global task reference
_keepalive_task = None


def start_keepalive():
    """
    Start the Railway keepalive background task.
    Call this once during FastAPI startup.

    Note: Must be called within an async context (e.g., FastAPI lifespan).
    """
    global _keepalive_task

    if _keepalive_task is not None:
        logger.warning("⚠️ Railway keepalive already running")
        return

    if not RAILWAY_URL:
        logger.warning("⚠️ DEPTH_ESTIMATION_URL or MIDAS_MCP_URL not set, keepalive disabled")
        return

    try:
        # Try to get the running event loop (FastAPI provides this)
        loop = asyncio.get_running_loop()
        _keepalive_task = loop.create_task(keepalive_loop())
        logger.info("✓ Railway keepalive background task created")
    except RuntimeError:
        # No running loop - we're not in an async context
        logger.warning("⚠️ No event loop running, keepalive disabled (call from FastAPI lifespan)")
        return


def stop_keepalive():
    """
    Stop the Railway keepalive background task.
    Call this during FastAPI shutdown (optional).
    """
    global _keepalive_task

    if _keepalive_task is not None:
        _keepalive_task.cancel()
        _keepalive_task = None
        logger.info("✓ Railway keepalive stopped")


def is_running() -> bool:
    """Check if keepalive service is running"""
    return _keepalive_task is not None and not _keepalive_task.done()
