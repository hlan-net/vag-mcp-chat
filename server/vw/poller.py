"""Background poller for VW EU Data Act telemetry.

Runs as an asyncio task alongside the FastMCP server. Every
VW_DATA_POLL_INTERVAL_SECONDS (default 14 min), it:
  1. Loads the current VW access token from the encrypted store.
  2. Requests a new data package from the EU Data Act portal.
  3. Waits up to 15 minutes for the ZIP to become available.
  4. Parses the ZIP and updates the in-memory VehicleState cache.

Tool calls read from the cache (see server/state.py). On the first call when
the cache is empty, trigger_immediate_refresh() is awaited instead.
"""

import asyncio
import logging
from datetime import datetime, timezone

from server.auth.token_store import token_store
from server.settings import settings
from server.vw.client import VWDataActClient
from server.vw.models import VehicleState
from server.vw.parser import parse_zip

logger = logging.getLogger(__name__)


class DataPoller:
    def __init__(self) -> None:
        self._cache: dict[str, VehicleState] = {}
        self._task: asyncio.Task | None = None
        self._refresh_events: dict[str, asyncio.Event] = {}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._task = asyncio.create_task(self._poll_loop(), name="vw-poller")
        logger.info("VW data poller started (interval=%ds)", settings.vw_data_poll_interval_seconds)

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    # ── Public API (used by tools) ─────────────────────────────────────────────

    def get_cached_state(self, vin: str) -> VehicleState | None:
        return self._cache.get(vin)

    async def trigger_immediate_refresh(self, vin: str) -> VehicleState | None:
        """Fetch a fresh data package now, waiting up to 15 minutes."""
        event = self._refresh_events.setdefault(vin, asyncio.Event())
        event.clear()
        asyncio.create_task(self._fetch_for_vin(vin), name=f"vw-refresh-{vin}")
        try:
            await asyncio.wait_for(event.wait(), timeout=960)
        except asyncio.TimeoutError:
            logger.warning("Immediate refresh timed out for VIN %s", vin)
        return self._cache.get(vin)

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_all_vins()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Poller iteration failed")
            await asyncio.sleep(settings.vw_data_poll_interval_seconds)

    async def _poll_all_vins(self) -> None:
        tokens = await token_store.load()
        if tokens is None:
            logger.warning(
                "No VW tokens found. Run `python -m server.setup` first."
            )
            return

        client = VWDataActClient(tokens.access_token)
        try:
            vehicles = await client.list_vehicles()
        except Exception:
            logger.exception("Failed to list vehicles")
            return

        vins = [v.get("vin") for v in vehicles if v.get("vin")]
        if settings.vw_default_vin and settings.vw_default_vin not in vins:
            vins.append(settings.vw_default_vin)
        if not vins and settings.vw_default_vin:
            vins = [settings.vw_default_vin]

        for vin in vins:
            await self._fetch_for_vin(vin)

    async def _fetch_for_vin(self, vin: str) -> None:
        tokens = await token_store.load()
        if tokens is None:
            return

        client = VWDataActClient(tokens.access_token)
        try:
            package_id = await client.request_data_package(vin)
            download_url = await client.poll_for_package(package_id)
            zip_bytes = await client.download_zip(download_url)
        except Exception:
            logger.exception("Failed to fetch data package for VIN %s", vin)
            return

        state = parse_zip(zip_bytes, default_vin=vin)
        if state is not None:
            self._cache[vin] = state
            logger.info(
                "Updated cache for VIN %s (recorded_at=%s)", vin, state.recorded_at
            )
            event = self._refresh_events.get(vin)
            if event:
                event.set()
        else:
            logger.warning("ZIP parsing yielded no data for VIN %s", vin)


data_poller = DataPoller()
