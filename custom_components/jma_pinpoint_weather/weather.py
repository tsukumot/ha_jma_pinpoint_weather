import logging
from datetime import timedelta

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import device_info
from .forecast import get_forecast

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    lat = entry.data["latitude"]
    lon = entry.data["longitude"]

    async def _update():
        return await hass.async_add_executor_job(get_forecast, lat, lon)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name="forecast",
        update_method=_update,
        update_interval=timedelta(minutes=15),
    )
    coordinator.data = {"hourly": [], "min_temp": None, "max_temp": None}
    async_add_entities([RainWeather(coordinator, entry)])
    entry.async_create_background_task(
        hass, coordinator.async_refresh(), "jma_pinpoint_weather first refresh"
    )

class RainWeather(CoordinatorEntity, WeatherEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_name = entry.data["name"]
        self._attr_unique_id = entry.unique_id
        self._attr_device_info = device_info(entry)

    @callback
    def _handle_coordinator_update(self):
        self.hass.async_create_task(self.async_update_listeners(["hourly"]))
        super()._handle_coordinator_update()

    # ---- 現在の状態(予報の先頭を使う) ----
    @property
    def condition(self):
        return self.coordinator.data["hourly"][0]["condition"] if self.coordinator.data["hourly"] else None

    @property
    def native_temperature(self):
        return self.coordinator.data["hourly"][0]["temperature"] if self.coordinator.data["hourly"] else None

    # ---- 予報 ----
    async def async_forecast_hourly(self) -> list[Forecast] | None:
        # forecast.py のキー名を、HAが決めているキー名に変換して返す
        return [
            {
                "datetime": item["datetime"],
                "condition": item["condition"],
                "native_temperature": item["temperature"],
                "native_precipitation": item["precipitation"],
            }
            for item in self.coordinator.data["hourly"]
        ]

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self.coordinator.data["min_temp"] is not None:
            attrs["min_temp"] = self.coordinator.data["min_temp"]
        if self.coordinator.data["max_temp"] is not None:
            attrs["max_temp"] = self.coordinator.data["max_temp"]
        return attrs
