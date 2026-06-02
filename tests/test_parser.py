"""Unit tests for the VW telemetry ZIP parser."""

import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from server.vw.parser import parse_zip, parse_telemetry_dict


def _make_zip(files: dict[str, str | dict]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            if isinstance(content, dict):
                content = json.dumps(content)
            zf.writestr(name, content)
    return buf.getvalue()


class TestParseTelemetryDict:
    def test_battery_fields(self):
        data = {
            "batteryLevel": 78.5,
            "remainingRange": 245.0,
            "chargingStatus": "not_charging",
            "timestamp": "2026-06-02T12:00:00Z",
        }
        state = parse_telemetry_dict("WVW123", data)
        assert state.battery_level_pct == pytest.approx(78.5)
        assert state.range_km == pytest.approx(245.0)
        assert state.is_charging is False
        assert state.vin == "WVW123"

    def test_location_fields(self):
        data = {
            "lat": 52.3731,
            "lon": 4.8922,
            "odometer": 15000.0,
            "timestamp": 1748865600,
        }
        state = parse_telemetry_dict("WVW123", data)
        assert state.latitude == pytest.approx(52.3731)
        assert state.longitude == pytest.approx(4.8922)
        assert state.odometer_km == pytest.approx(15000.0)

    def test_climate_fields(self):
        data = {
            "interiorTemperature": 22.0,
            "exteriorTemperature": 5.0,
            "climatisationActive": True,
            "timestamp": "2026-06-02T12:00:00Z",
        }
        state = parse_telemetry_dict("WVW123", data)
        assert state.interior_temp_c == pytest.approx(22.0)
        assert state.exterior_temp_c == pytest.approx(5.0)
        assert state.climate_active is True

    def test_missing_fields_are_none(self):
        state = parse_telemetry_dict("WVW123", {"timestamp": "2026-06-02T12:00:00Z"})
        assert state.battery_level_pct is None
        assert state.latitude is None
        assert state.is_charging is None

    def test_vin_from_data_takes_precedence(self):
        data = {"vin": "WVWFROMDATA", "timestamp": "2026-06-02T12:00:00Z"}
        state = parse_telemetry_dict("WVWDEFAULT", data)
        assert state.vin == "WVWFROMDATA"

    def test_charging_active_from_string(self):
        data = {"chargingStatus": "charging", "timestamp": "2026-06-02T12:00:00Z"}
        state = parse_telemetry_dict("WVW123", data)
        assert state.is_charging is True

    def test_soc_alias(self):
        data = {"soc": 55.0, "timestamp": "2026-06-02T12:00:00Z"}
        state = parse_telemetry_dict("WVW123", data)
        assert state.battery_level_pct == pytest.approx(55.0)


class TestParseZip:
    def test_parses_vehicle_json(self):
        payload = {
            "vin": "WVWTEST",
            "batteryLevel": 90.0,
            "remainingRange": 300.0,
            "timestamp": "2026-06-02T12:00:00Z",
        }
        zip_bytes = _make_zip({"vehicle_status.json": payload})
        state = parse_zip(zip_bytes, default_vin="WVWTEST")
        assert state is not None
        assert state.battery_level_pct == pytest.approx(90.0)

    def test_returns_none_for_empty_zip(self):
        zip_bytes = _make_zip({})
        result = parse_zip(zip_bytes, default_vin="WVW123")
        assert result is None

    def test_returns_none_for_garbage_bytes(self):
        result = parse_zip(b"not a zip file at all", default_vin="WVW123")
        assert result is None

    def test_handles_array_telemetry(self):
        records = [
            {"batteryLevel": 50.0, "timestamp": "2026-06-02T11:00:00Z"},
            {"batteryLevel": 60.0, "timestamp": "2026-06-02T12:00:00Z"},
        ]
        zip_bytes = _make_zip({"telemetry.json": records})
        state = parse_zip(zip_bytes, default_vin="WVW123")
        assert state is not None
        assert state.battery_level_pct == pytest.approx(60.0)

    def test_skips_non_json_files(self):
        zip_bytes = _make_zip(
            {"readme.txt": "no data here", "vehicle.json": {"batteryLevel": 42.0, "timestamp": "2026-06-02T12:00:00Z"}}
        )
        state = parse_zip(zip_bytes, default_vin="WVW123")
        assert state is not None
        assert state.battery_level_pct == pytest.approx(42.0)
