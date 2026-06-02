"""HTTP client for the VW EU Data Act portal.

The portal is not a real-time REST API — it is a batch data platform. The
expected flow is:
  1. POST /data-packages  → triggers generation of a telemetry ZIP
  2. GET  /data-packages/{id}  → poll until status == "ready"
  3. GET  the download URL from the response → stream the ZIP bytes

NOTE: The exact endpoint paths below are educated guesses based on the portal's
published documentation and community integrations. Adjust them after verifying
against the portal's OpenAPI spec or by inspecting real network traffic.
"""

import asyncio
import logging

import httpx

from server.settings import settings

logger = logging.getLogger(__name__)

_BASE = settings.vw_oidc_issuer.rstrip("/")
_PACKAGES_ENDPOINT = f"{_BASE}/api/v1/data-packages"


class VWDataActClient:
    def __init__(self, access_token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

    async def request_data_package(self, vin: str) -> str:
        """Ask the portal to generate a telemetry package. Returns a package ID."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _PACKAGES_ENDPOINT,
                headers=self._headers,
                json={"vin": vin},
            )
            resp.raise_for_status()
            data = resp.json()
            package_id: str = data.get("id") or data.get("packageId") or data["id"]
            logger.info("Data package %s requested for VIN %s", package_id, vin)
            return package_id

    async def poll_for_package(self, package_id: str, timeout_s: int = 900) -> str:
        """Poll until the package is ready and return its download URL."""
        deadline = asyncio.get_event_loop().time() + timeout_s
        poll_url = f"{_PACKAGES_ENDPOINT}/{package_id}"

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise TimeoutError(
                        f"Data package {package_id} not ready within {timeout_s}s"
                    )

                resp = await client.get(poll_url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()

                status = (data.get("status") or "").lower()
                logger.debug("Package %s status: %s", package_id, status)

                if status == "ready":
                    url: str = data.get("downloadUrl") or data.get("url") or data["downloadUrl"]
                    return url
                if status in {"failed", "error"}:
                    raise RuntimeError(f"Data package {package_id} failed: {data}")

                # Not ready yet; wait 30 s before the next poll
                await asyncio.sleep(30)

    async def download_zip(self, download_url: str) -> bytes:
        """Download the telemetry ZIP and return its raw bytes."""
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
            resp = await client.get(download_url, headers=self._headers)
            resp.raise_for_status()
            return resp.content

    async def list_vehicles(self) -> list[dict]:
        """Return the vehicles linked to the authenticated VW account."""
        vehicles_url = f"{_BASE}/api/v1/vehicles"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(vehicles_url, headers=self._headers)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, list) else data.get("vehicles", [])
