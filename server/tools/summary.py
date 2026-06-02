from fastmcp.server.auth import require_scopes

from server import mcp_instance as mcp
from server import state
from server.settings import settings


@mcp.tool(auth=require_scopes("vehicle:read"))
async def get_vehicle_summary(vin: str = "") -> dict:
    """Return a complete snapshot of all available vehicle telemetry fields.

    Use this when the user asks a general question about their car's status.

    Args:
        vin: Vehicle Identification Number. Defaults to VW_DEFAULT_VIN if empty.
    """
    vin = vin or settings.vw_default_vin
    if not vin:
        return {"error": "No VIN provided and VW_DEFAULT_VIN is not configured."}

    vehicle_state = state.data_poller.get_cached_state(vin)
    if vehicle_state is None:
        vehicle_state = await state.data_poller.trigger_immediate_refresh(vin)
    if vehicle_state is None:
        return {"error": "No data available yet. Try again in a few minutes."}

    return {
        "vin": vehicle_state.vin,
        "battery_level_pct": vehicle_state.battery_level_pct,
        "range_km": vehicle_state.range_km,
        "is_charging": vehicle_state.is_charging,
        "charging_power_kw": vehicle_state.charging_power_kw,
        "charge_target_pct": vehicle_state.charge_target_pct,
        "latitude": vehicle_state.latitude,
        "longitude": vehicle_state.longitude,
        "interior_temp_c": vehicle_state.interior_temp_c,
        "exterior_temp_c": vehicle_state.exterior_temp_c,
        "climate_active": vehicle_state.climate_active,
        "odometer_km": vehicle_state.odometer_km,
        "data_age_seconds": round(vehicle_state.data_age_seconds),
        "recorded_at": vehicle_state.recorded_at.isoformat(),
    }
