import logging
import math
from datetime import datetime, timedelta, timezone
from io import BytesIO

import requests
from PIL import Image
from .const import BASE, BASE_NC

_LOGGER = logging.getLogger(__name__)

COLOR_DICT_WM = {
    (255, 170, 0): "sunny",
    (170, 170, 170): "cloudy",
    (0, 65, 255): "rainy",
    (160, 210, 255): "snowy-rainy",
    (255, 255, 255): "snowy",
}
COLOR_DICT_R3 = {
    (160, 209, 255): 1,
    (34, 140, 255): 3,
    (1, 65, 255): 5,
    (255, 245, 0): 7,
    (255, 153, 0): 10,
}
COLOR_DICT_S3 = {
    (160, 209, 255): 1,
    (34, 140, 255): 2,
    (1, 65, 255): 3,
}
COLOR_DICT_NC = {
    (242, 242, 255): 1,
    (160, 209, 255): 5,
    (34, 140, 255): 10,
    (1, 65, 255): 20,
    (255, 245, 0): 30,
    (255, 153, 0): 50,
    (254, 41, 0): 80,
    (180, 0, 104): 100,
}
COLOR_DICT_LNC = {
    (200, 1, 255): 4,
    (254, 41, 0): 3,
    (254, 170, 2): 2,
    (255, 245, 0): 1,
}


def parse_time(s):
    # "20261110090000" → UTC
    return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def get_target_times():
    res = requests.get(f"{BASE}/targetTimes.json", timeout=10)
    res.raise_for_status()
    return res.json()


# ---- temperature(geojson) ----
def get_temp_geojson(basetime, validtime, element="temp_point"):
    url = f"{BASE}/{basetime}/none/{validtime}/surf/{element}/data.geojson"
    res = requests.get(url, params={"id": element}, timeout=30)
    res.raise_for_status()
    return res.json()


def get_first_minmax(times, lat, lon):
    result = {}
    # validtimeの古い順に並べて、最初に見つかったものを使う
    for t in sorted(times, key=lambda t: t["validtime"]):
        for key, element in (("min_temp", "min_temp_point"), ("max_temp", "max_temp_point")):
            if key not in result and element in t["elements"]:  # まだ取っていなくて、値があるとき
                geo = get_temp_geojson(t["basetime"], t["validtime"], element)
                result[key] = nearest_temp(geo, lat, lon)
    return result


def nearest_temp(geojson, lat, lon):
    best_dist = None
    best_value = None
    for f in geojson["features"]:
        x, y = f["geometry"]["coordinates"]  # x=経度, y=緯度
        dist = (x - lon) ** 2 + (y - lat) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_value = f["properties"]["value"]
    return int(best_value)


# ---- weather(PNG tile) ----
def latlon_to_tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return int(x), int(y), x - int(x), y - int(y)  # タイル番号と、タイル内の位置(0〜1)


def get_pixel(basetime, validtime, element, lat, lon, z=8, base=BASE):
    tx, ty, fx, fy = latlon_to_tile(lat, lon, z)
    url = f"{base}/{basetime}/none/{validtime}/surf/{element}/{z}/{tx}/{ty}.png"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    img = Image.open(BytesIO(res.content)).convert("RGBA")
    return img.getpixel((int(fx * img.width), int(fy * img.height)))


def color_to_value(rgba, color_dict, default=None):
    r, g, b, a = rgba
    if a == 0:
        return default  # 透明のとき
    nearest = min(
        color_dict,
        key=lambda c: (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2,
    )
    return color_dict[nearest]


# ---- まとめ ----
_cache = {}  # {(緯度, 経度): (前回のtargetTimes, 前回の予報)}


def get_forecast(lat, lon):
    times = get_target_times()
    basetime = times[0]["basetime"]
    cached = _cache.get((lat, lon))
    if cached is not None and cached[0] == basetime:
        return cached[1]  # targetTimesが同じなら、前回の予報をそのまま返す

    forecast = []
    sorted_times = sorted(times, key=lambda t: t["validtime"])  # 古い順
    for i, t in enumerate(sorted_times):
        if "temp_point" not in t["elements"]:
            continue
        # 次の予報時刻のwmがない(最後の1件など)ものは、天気が決まらないので飛ばす
        if i + 1 >= len(sorted_times) or "wm" not in sorted_times[i + 1]["elements"]:
            continue

        nxt = sorted_times[i + 1]
        args = (nxt["basetime"], nxt["validtime"])
        rain = color_to_value(get_pixel(*args, "r3", lat, lon), COLOR_DICT_R3, default=0)
        if rain > 5:
            condition = "pouring"
        else:
            condition = color_to_value(get_pixel(*args, "wm", lat, lon), COLOR_DICT_WM)
        # snow = color_to_value(get_pixel(*args, "s3", lat, lon), COLOR_DICT_S3, default=0)
        geo = get_temp_geojson(t["basetime"], t["validtime"])
        forecast.append({
            "datetime": parse_time(t["validtime"]).isoformat(),
            "condition": condition,
            "temperature": nearest_temp(geo, lat, lon),
            "precipitation": rain,
            # "snowfall": snow,
        })

    forecast.sort(key=lambda f: f["datetime"])
    result = {"hourly": forecast, "min_temp": None, "max_temp": None}
    result.update(get_first_minmax(times, lat, lon))  # 値があれば上書きする
    _cache[(lat, lon)] = (basetime, result)
    return result


# ---- ナウキャスト(直近1時間の雨量) ----
def get_nc_times(num=2):
    res = requests.get(f"{BASE_NC}/targetTimes_N{num}.json", timeout=10)
    res.raise_for_status()
    return res.json()


_cache_nc = {}  # {(緯度, 経度): (前回のtimes, 前回の合計)}


def get_nowcast(lat, lon):
    times = get_nc_times(2)
    basetime = times[0]["basetime"]
    cached = _cache_nc.get((lat, lon))
    if cached is not None and cached[0] == basetime:
        return cached[1]

    nowcast = []
    for t in times:
        if "hrpns" not in t["elements"]:
            continue
        pixel = get_pixel(
            t["basetime"], t["validtime"], "hrpns", lat, lon, z=10, base=BASE_NC
        )
        nowcast.append({
            "basetime": t["basetime"],
            "datetime": parse_time(t["validtime"]).isoformat(),
            "rain": color_to_value(pixel, COLOR_DICT_NC, default=0)
        })

    nowcast.sort(key=lambda n: n["datetime"])  # 時刻の古い順

    _cache_nc[(lat, lon)] = (basetime, nowcast)
    return nowcast


def get_rain_next_hour(lat, lon):
    nowcast = get_nowcast(lat, lon)
    return round(sum(n["rain"] for n in nowcast) * 5 / 60, 1)


def already_raining(lat, lon):
    nowcast = get_nowcast(lat, lon)
    if not nowcast:
        return False
    basetime = nowcast[0]["basetime"]
    measured = get_pixel(basetime, basetime, "hrpns", lat, lon, z=10, base=BASE_NC)
    return color_to_value(measured, COLOR_DICT_NC, default=0) > 0

if __name__ == "__main__":
    for item in get_forecast(35.68, 139.77)["hourly"]:
        print(item)
        print(get_rain_next_hour(35.68, 139.77)) 