from datetime import timedelta

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfTemperature

from .forecast import get_forecast

# 何分ごとに async_update を呼ぶか(未指定だと30秒ごとになり、気象庁に負荷をかける)
SCAN_INTERVAL = timedelta(minutes=30)


async def async_setup_entry(hass, entry, async_add_entities):
    # update_before_add=True: 追加する前に1回 async_update を実行する
    async_add_entities([RainWeather(entry)], update_before_add=True)


class RainWeather(WeatherEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_supported_features = WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, entry):
        self._lat = entry.data["latitude"]
        self._lon = entry.data["longitude"]
        self._attr_name = entry.data["name"]
        self._attr_unique_id = entry.unique_id
        self._forecast = []  # forecast.py の結果(取得前は空)
        self._min_temp = None
        self._max_temp = None

    async def async_update(self):
        result = await self.hass.async_add_executor_job(
            get_forecast, self._lat, self._lon
        )
        self._forecast = result["hourly"]
        self._min_temp = result["min_temp"]
        self._max_temp = result["max_temp"]
        await self.async_update_listeners(["hourly"])

    # ---- 現在の状態(予報の先頭を使う) ----
    @property
    def condition(self):
        return self._forecast[0]["condition"] if self._forecast else None

    @property
    def native_temperature(self):
        return self._forecast[0]["temperature"] if self._forecast else None

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
            for item in self._forecast
        ]

    @property
    def extra_state_attributes(self):
        attrs = {}
        if self._min_temp is not None:
            attrs["min_temp"] = self._min_temp
        if self._max_temp is not None:
            attrs["max_temp"] = self._max_temp
        return attrs