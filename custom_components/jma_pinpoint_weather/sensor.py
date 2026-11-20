import logging
from datetime import datetime, timedelta

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
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.util import dt as dt_util

from .amedas import get_amedas
from .const import CONF_NC_INTERVAL, DEF_NC_INTERVAL, device_info
from .forecast import get_nowcast, already_raining, parse_time

_LOGGER = logging.getLogger(__name__)

_MS = UnitOfSpeed.METERS_PER_SECOND
_CM = UnitOfLength.CENTIMETERS
_C = UnitOfTemperature.CELSIUS
_HPA = UnitOfPressure.HPA
_SDC = SensorDeviceClass
# 気温の観測所から作るセンサー(降水以外)
TEMP_SENSORS = {
    "temp": ("気温", _C, _SDC.TEMPERATURE),
    "humidity": ("湿度", PERCENTAGE, _SDC.HUMIDITY),
    "pressure": ("現地気圧", _HPA, _SDC.ATMOSPHERIC_PRESSURE),
    "normalPressure": ("海面気圧", _HPA, _SDC.ATMOSPHERIC_PRESSURE),
    "wind": ("風速", _MS, _SDC.WIND_SPEED),
    "windDirection": ("風向", None, None),
    "sun10m": ("日照時間(10分間)", UnitOfTime.MINUTES, None),
    "sun1h": ("日照時間(01時間)", UnitOfTime.HOURS, None),
    "snow": ("積雪深", _CM, None),
    "snow1h": ("降雪量(01時間)", _CM, None),
    "snow3h": ("降雪量(03時間)", _CM, None),
    "snow6h": ("降雪量(06時間)", _CM, None),
    "snow12h": ("降雪量(12時間)", _CM, None),
    "snow24h": ("降雪量(24時間)", _CM, None),
}

# 降水の観測所から作るセンサー
_MM = UnitOfPrecipitationDepth.MILLIMETERS
_RAIN = _SDC.PRECIPITATION
PRECIP_SENSORS = {
    "precipitation10m": ("降水量(10分間)", _MM, _RAIN),
    "precipitation1h": ("降水量(01時間)", _MM, _RAIN),
    "precipitation3h": ("降水量(03時間)", _MM, _RAIN),
    "precipitation24h": ("降水量(24時間)", _MM, _RAIN),
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

    def _fetch_nc():
        return {
            "nowcast": get_nowcast(lat, lon),
            "raining": already_raining(lat, lon),
        }

    async def _update_nc():
        return await hass.async_add_executor_job(_fetch_nc)

    interval = entry.options.get(CONF_NC_INTERVAL, DEF_NC_INTERVAL)
    nc_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name="nowcast",
        update_method=_update_nc,
        update_interval=timedelta(minutes=interval),
    )
    await nc_coordinator.async_config_entry_first_refresh()
    entities.append(RainStartSensor(nc_coordinator, entry))

    async_add_entities(entities)


class AmedasSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, group, key, label, unit, device_class):
        super().__init__(coordinator)
        self._group = group  # "temp" か "precip"(どの観測所のデータか)
        self._key = key      # "humidity" など(観測値JSONの項目名)
        self._attr_name = f"{entry.data['name']} アメダス{label}"
        self._attr_unique_id = f"{entry.unique_id}_amedas_{key}"
        self._attr_device_info = device_info(entry)
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


class RainStartSensor(CoordinatorEntity, SensorEntity):
    _attr_device_class = _SDC.TIMESTAMP

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._attr_name = f"{entry.data['name']} ナウキャスト降り始め"
        self._attr_unique_id = f"{entry.unique_id}_rain_start"
        self._attr_device_info = device_info(entry)
        self._start = None  # 覚えておく降り始め時刻
        self._update_start()  # 最初の1回

    def _update_start(self):
        data = self.coordinator.data

        if not data["raining"]:
            # 降っていない: 今まで通り
            self._start = None
            for item in data["nowcast"]:
                if item["rain"] > 0:
                    self._start = datetime.fromisoformat(item["datetime"])
                    break
        else:
            # 降っている: 値がない、または basetime より未来なら basetime にする
            basetime = parse_time(data["nowcast"][0]["basetime"])
            if self._start is None or self._start > basetime:
                self._start = basetime

    @callback
    def _handle_coordinator_update(self):
        self._update_start()
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        return self._start

    @property
    def extra_state_attributes(self):
        return {
            "forecast": [
                {
                    "datetime": dt_util.as_local(
                        datetime.fromisoformat(item["datetime"])
                    ).isoformat(),
                    "rain": item["rain"],
                }
                for item in self.coordinator.data["nowcast"]
            ]
        }