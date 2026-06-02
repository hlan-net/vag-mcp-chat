"""Parse the VW EU Data Act telemetry ZIP into a VehicleState.

The EU Data Act portal delivers a ZIP archive every ~15 minutes. The exact
internal structure is not publicly documented; this parser discovers JSON/CSV
files within the archive and maps known field names to VehicleState fields.

If you receive a ZIP from the portal and the parsing produces None values, run
the server with DEBUG logging to see the full archive structure, then update
the field mappings below accordingly.
"""

import io
import json
import logging
import zipfile
from datetime import datetime, timezone

from server.vw.models import VehicleState

logger = logging.getLogger(__name__)

# ── Field name mappings ────────────────────────────────────────────────────────
# Keys are candidate field names found in VW telemetry JSON.
# Add new names as you discover them from real ZIP files.

_BATTERY_PCT_KEYS = {"batteryLevel", "battery_level", "soc", "stateOfCharge"}
_RANGE_KM_KEYS = {"remainingRange", "range_km", "cruisingRange", "electric_range"}
_IS_CHARGING_KEYS = {"chargingStatus", "isCharging", "charging_status"}
_CHARGING_KW_KEYS = {"chargingPower", "charging_power_kw", "powerDeliveredAc", "powerDeliveredDc"}
_CHARGE_TARGET_KEYS = {"targetSoC", "charge_target_pct", "chargingTargetPercent"}
_LAT_KEYS = {"latitude", "lat", "gps_lat"}
_LON_KEYS = {"longitude", "lon", "lng", "gps_lon"}
_INTERIOR_TEMP_KEYS = {"interiorTemperature", "interior_temp_c", "cabinTemperature"}
_EXTERIOR_TEMP_KEYS = {"exteriorTemperature", "exterior_temp_c", "outsideTemperature"}
_CLIMATE_KEYS = {"climatisationStatus", "climate_active", "climatisationActive"}
_ODO_KEYS = {"odometer", "odometer_km", "totalMileage", "mileage"}
_VIN_KEYS = {"vin", "vehicleIdentificationNumber"}
_TIMESTAMP_KEYS = {"timestamp", "recorded_at", "captureTime", "ts"}


def _pick(data: dict, candidates: set[str]) -> object | None:
    for key in candidates:
        if key in data:
            return data[key]
    return None


def _to_float(v: object) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _to_bool(v: object) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in {"true", "active", "charging", "on", "1"}
    if isinstance(v, (int, float)):
        return bool(v)
    return None


def _parse_ts(v: object) -> datetime:
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc)
    if isinstance(v, str):
        for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(v, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
    return datetime.now(tz=timezone.utc)


def parse_telemetry_dict(vin: str, data: dict) -> VehicleState:
    """Map a flat telemetry dict to VehicleState."""
    ts_raw = _pick(data, _TIMESTAMP_KEYS)
    return VehicleState(
        vin=str(_pick(data, _VIN_KEYS) or vin),
        battery_level_pct=_to_float(_pick(data, _BATTERY_PCT_KEYS)),
        range_km=_to_float(_pick(data, _RANGE_KM_KEYS)),
        is_charging=_to_bool(_pick(data, _IS_CHARGING_KEYS)),
        charging_power_kw=_to_float(_pick(data, _CHARGING_KW_KEYS)),
        charge_target_pct=_to_float(_pick(data, _CHARGE_TARGET_KEYS)),
        latitude=_to_float(_pick(data, _LAT_KEYS)),
        longitude=_to_float(_pick(data, _LON_KEYS)),
        interior_temp_c=_to_float(_pick(data, _INTERIOR_TEMP_KEYS)),
        exterior_temp_c=_to_float(_pick(data, _EXTERIOR_TEMP_KEYS)),
        climate_active=_to_bool(_pick(data, _CLIMATE_KEYS)),
        odometer_km=_to_float(_pick(data, _ODO_KEYS)),
        recorded_at=_parse_ts(ts_raw),
    )


def parse_zip(zip_bytes: bytes, default_vin: str = "") -> VehicleState | None:
    """Extract and parse telemetry from a VW EU Data Act ZIP archive."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            logger.debug("ZIP contains: %s", names)

            # Prefer JSON files containing "telemetry", "vehicle", or "status"
            json_files = [
                n for n in names
                if n.endswith(".json")
                and any(kw in n.lower() for kw in ("telemetry", "vehicle", "status", "data"))
            ]
            # Fall back to any JSON file
            if not json_files:
                json_files = [n for n in names if n.endswith(".json")]

            for fname in json_files:
                try:
                    raw = zf.read(fname)
                    data = json.loads(raw)
                    logger.debug("Parsing %s", fname)

                    # Handle top-level list (array of records) — use last/most recent
                    if isinstance(data, list) and data:
                        data = data[-1]

                    if not isinstance(data, dict):
                        continue

                    state = parse_telemetry_dict(default_vin, data)
                    if any(
                        v is not None
                        for v in (state.battery_level_pct, state.latitude, state.odometer_km)
                    ):
                        return state

                except Exception:
                    logger.debug("Skipping %s — parse error", fname, exc_info=True)

    except zipfile.BadZipFile:
        logger.error("Received bytes are not a valid ZIP archive")
    except Exception:
        logger.exception("Unexpected error parsing ZIP")

    return None
