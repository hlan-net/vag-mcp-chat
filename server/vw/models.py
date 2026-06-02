from datetime import datetime

from pydantic import BaseModel


class VehicleState(BaseModel):
    vin: str
    battery_level_pct: float | None = None
    range_km: float | None = None
    is_charging: bool | None = None
    charging_power_kw: float | None = None
    charge_target_pct: float | None = None
    latitude: float | None = None
    longitude: float | None = None
    interior_temp_c: float | None = None
    exterior_temp_c: float | None = None
    climate_active: bool | None = None
    odometer_km: float | None = None
    recorded_at: datetime

    @property
    def data_age_seconds(self) -> float:
        return (datetime.now(tz=self.recorded_at.tzinfo) - self.recorded_at).total_seconds()
