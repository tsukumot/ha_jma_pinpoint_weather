import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .amedas import get_amedas

_LOGGER = logging.getLogger(__name__)

# 気温の観測所から作るセンサー(降水以外)
TEMP_SENSORS = {
    "temp": ("気温", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
    "humidity": ("湿度", PERCENTAGE, SensorDeviceClass.HUMIDITY),
    "pressure": ("現地気圧", UnitOfPressure.HPA, SensorDeviceClass.ATMOSPHERIC_PRESSURE),
    "normalPressure": ("海面気圧", UnitOfPressure.HPA, SensorDeviceClass.ATMOSPHERIC_PRESSURE),
    "wind": ("風速", UnitOfSpeed.METERS_PER_SECOND, SensorDeviceClass.WIND_SPEED),
    "windDirection": ("風向", None, None),
    "sun10m": ("10分間日照時間", UnitOfTime.MINUTES, None),
    "sun1h": ("1時間日照時間", UnitOfTime.HOURS, None),
    "snow": ("積雪深", UnitOfLength.CENTIMETERS, None),
    "snow1h": ("1時間降雪量", UnitOfLength.CENTIMETERS, None),
    "snow3h": ("3時間降雪量", UnitOfLength.CENTIMETERS, None),
    "snow6h": ("6時間降雪量", UnitOfLength.CENTIMETERS, None),
    "snow12h": ("12時間降雪量", UnitOfLength.CENTIMETERS, None),
    "snow24h": ("24時間降雪量", UnitOfLength.CENTIMETERS, None),
}

# 降水の観測所から作るセンサー
_MM = UnitOfPrecipitationDepth.MILLIMETERS
_RAIN = SensorDeviceClass.PRECIPITATION
PRECIP_SENSORS = {
    "precipitation10m": ("10分間降水量", _MM, _RAIN),
    "precipitation1h": ("1時間降水量", _MM, _RAIN),
    "precipitation3h": ("3時間降水量", _MM, _RAIN),
    "precipitation24h": ("24時間降水量", _MM, _RAIN),
}


async def async_setup_entry(hass, entry, async_add_entities):
    lat = entry.data["latitude"]
    lon = entry.data["longitude"]

    async def _update():
        return await hass.async_add_executor_job(get_amedas, lat, lon)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name="amedas",
        update_method=_update,
        update_interval=timedelta(minutes=10),
    )
    await coordinator.async_config_entry_first_refresh()

    entities = []
    for group, defs in (("temp", TEMP_SENSORS), ("precip", PRECIP_SENSORS)):
        st = coordinator.data.get(group)
        if not st:
            continue  # この種類の観測所が見つからなかった
        for key, (label, unit, device_class) in defs.items():
            if key in st["values"]:  # その観測所が持っている項目だけ作る
                entities.append(
                    AmedasSensor(coordinator, entry, group, key, label, unit, device_class)
                )
    async_add_entities(entities)


class AmedasSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, group, key, label, unit, device_class):
        super().__init__(coordinator)
        self._group = group  # "temp" か "precip"(どの観測所のデータか)
        self._key = key      # "humidity" など(観測値JSONの項目名)
        self._attr_name = f"{entry.data['name']} アメダス{label}"
        self._attr_unique_id = f"{entry.unique_id}_amedas_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    @property
    def native_value(self):
        st = self.coordinator.data.get(self._group)
        return st["values"].get(self._key) if st else None

    @property
    def extra_state_attributes(self):
        st = self.coordinator.data.get(self._group)
        if not st:
            return {}
        return {
            "station_name": st["name"],
            "station_id": st["id"],
            "observed_at": self.coordinator.data["observed_at"],
        }