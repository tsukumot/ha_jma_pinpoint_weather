from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo


DOMAIN = "jma_pinpoint_weather"
BASE = "https://www.jma.go.jp/bosai/jmatile/data/wdist"
BASE_NC = "https://www.jma.go.jp/bosai/jmatile/data/nowc"

AMEDAS_TABLE_URL = "https://www.jma.go.jp/bosai/amedas/const/amedastable.json"
AMEDAS_LATEST_URL = "https://www.jma.go.jp/bosai/amedas/data/latest_time.txt"
AMEDAS_MAP_URL = "https://www.jma.go.jp/bosai/amedas/data/map/{ts}.json"

CONF_NC_INTERVAL = "nc_interval"
CONF_NC_THRESHOLD = "nc_threshold"
CONF_LNC_THRESHOLD = "lnc_threshold"
CONF_GNC_THRESHOLD = "gnc_threshold"
DEF_NC_INTERVAL = 5
MIN_NC_INTERVAL = 5
MAX_NC_INTERVAL = 60
DEF_NC_THRESHOLD = 4
MIN_NC_THRESHOLD = 1
MAX_NC_THRESHOLD = 5
DEF_LNC_THRESHOLD = 2
MIN_LNC_THRESHOLD = 1
MAX_LNC_THRESHOLD = 4
DEF_GNC_THRESHOLD = 2
MIN_GNC_THRESHOLD = 1
MAX_GNC_THRESHOLD = 2

def device_info(entry):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},  # このデバイスの身分証。3つのクラスで同じ値にする
        name=entry.data["name"],
        manufacturer="気象庁",
        entry_type=DeviceEntryType.SERVICE,  # 物理機器ではなくサービス扱い
    )