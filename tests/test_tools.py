"""Integration-style tests for MCP tool functions.

These tests patch `server.state.data_poller` — the tools access `data_poller`
via the `state` module reference (not a direct import), so the patch correctly
intercepts all tool calls without needing to know each tool module's import.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.vw.models import VehicleState

_NOW = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)

_SAMPLE_STATE = VehicleState(
    vin="WVWTEST123",
    battery_level_pct=78.5,
    range_km=240.0,
    is_charging=False,
    charging_power_kw=None,
    charge_target_pct=80.0,
    latitude=52.3731,
    longitude=4.8922,
    interior_temp_c=21.0,
    exterior_temp_c=8.0,
    climate_active=False,
    odometer_km=12345.0,
    recorded_at=_NOW,
)


def _make_poller_mock(state: VehicleState | None) -> MagicMock:
    mock = MagicMock()
    mock.get_cached_state.return_value = state
    mock.trigger_immediate_refresh = AsyncMock(return_value=state)
    return mock


class TestGetVehicleBattery:
    @pytest.mark.asyncio
    async def test_returns_battery_fields(self):
        from server.tools.battery import get_vehicle_battery

        with patch("server.state.data_poller", _make_poller_mock(_SAMPLE_STATE)):
            result = await get_vehicle_battery(vin="WVWTEST123")

        assert result["battery_level_pct"] == pytest.approx(78.5)
        assert result["range_km"] == pytest.approx(240.0)
        assert "data_age_seconds" in result
        assert "recorded_at" in result

    @pytest.mark.asyncio
    async def test_no_data_returns_error(self):
        from server.tools.battery import get_vehicle_battery

        with patch("server.state.data_poller", _make_poller_mock(None)):
            result = await get_vehicle_battery(vin="WVWTEST123")

        assert "error" in result


class TestGetVehicleLocation:
    @pytest.mark.asyncio
    async def test_returns_location_fields(self):
        from server.tools.location import get_vehicle_location

        with patch("server.state.data_poller", _make_poller_mock(_SAMPLE_STATE)):
            result = await get_vehicle_location(vin="WVWTEST123")

        assert result["latitude"] == pytest.approx(52.3731)
        assert result["longitude"] == pytest.approx(4.8922)
        assert result["odometer_km"] == pytest.approx(12345.0)


class TestGetClimateStatus:
    @pytest.mark.asyncio
    async def test_returns_climate_fields(self):
        from server.tools.climate import get_climate_status

        with patch("server.state.data_poller", _make_poller_mock(_SAMPLE_STATE)):
            result = await get_climate_status(vin="WVWTEST123")

        assert result["interior_temp_c"] == pytest.approx(21.0)
        assert result["exterior_temp_c"] == pytest.approx(8.0)
        assert result["climate_active"] is False


class TestGetChargingStatus:
    @pytest.mark.asyncio
    async def test_returns_charging_fields(self):
        from server.tools.charging import get_charging_status

        with patch("server.state.data_poller", _make_poller_mock(_SAMPLE_STATE)):
            result = await get_charging_status(vin="WVWTEST123")

        assert result["is_charging"] is False
        assert result["charge_target_pct"] == pytest.approx(80.0)


class TestGetVehicleSummary:
    @pytest.mark.asyncio
    async def test_returns_all_fields(self):
        from server.tools.summary import get_vehicle_summary

        with patch("server.state.data_poller", _make_poller_mock(_SAMPLE_STATE)):
            result = await get_vehicle_summary(vin="WVWTEST123")

        expected_keys = {
            "vin", "battery_level_pct", "range_km", "is_charging",
            "charging_power_kw", "charge_target_pct", "latitude", "longitude",
            "interior_temp_c", "exterior_temp_c", "climate_active", "odometer_km",
            "data_age_seconds", "recorded_at",
        }
        assert expected_keys.issubset(result.keys())
