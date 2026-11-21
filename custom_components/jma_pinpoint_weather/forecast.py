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
    (242, 242, 255): "snowy",
}
COLOR_DICT_R3 = {
    (160, 210, 255): 1,
    (33, 140, 255): 3,
    (0, 65, 255): 5,
    (255, 245, 0): 7,
    (255, 153, 0): 10,
}
COLOR_DICT_S3 = {
    (160, 210, 255): 1,
    (33, 140, 255): 2,
    (0, 65, 255): 3,
}
COLOR_DICT_NC = {
    (242, 242, 255): 1,
    (160, 210, 255): 5,
    (33, 140, 255): 10,
    (0, 65, 255): 20,
    (255, 245, 0): 30,
    (255, 153, 0): 50,
    (255, 40, 0): 80,
    (180, 0, 104): 100,
}
COLOR_DICT_LNC = {
    (200, 0, 255): 4,
    (255, 40, 0): 3,
    (255, 170, 0): 2,
    (255, 245, 0): 1,
}
COLOR_DICT_GNC = {
    (255, 40, 0): 2,
    (250, 245, 0): 1,
}
# ナウキャストの種類ごとのズーム(雨は10、雷・竜巻は8が最大)
NC_ZOOM = {"rain": 10, "thunder": 8, "tornado": 8}


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


# ---- ナウキャストJSON ----
def get_nc_times(num=2):
    res = requests.get(f"{BASE_NC}/targetTimes_N{num}.json", timeout=10)
    res.raise_for_status()
    return res.json()


_cache_nc = {}  # {(緯度, 経度, 種類): (前回のtimes, 前回の合計)}


def get_nowcast(lat, lon, trg="rain"):
    if trg == "rain":
        num, element, colors = 2, "hrpns", COLOR_DICT_NC
    elif trg == "thunder":
        num, element, colors = 3, "thns", COLOR_DICT_LNC
    elif trg == "tornado":
        num, element, colors = 3, "trns", COLOR_DICT_GNC
    else:
        raise ValueError(f"未対応のtrg: {trg}")
    times = get_nc_times(num)
    basetime = times[0]["basetime"]
    cached = _cache_nc.get((lat, lon, trg))
    if cached is not None and cached[0] == basetime:
        return cached[1]

    nowcast = []
    for t in times:
        if element not in t["elements"]:
            continue
        if t["basetime"] != basetime:
            continue
        pixel = get_pixel(
            t["basetime"], t["validtime"], element, lat, lon, z=NC_ZOOM[trg], base=BASE_NC
        )
        nowcast.append({
            "basetime": t["basetime"],
            "datetime": parse_time(t["validtime"]).isoformat(),
            trg: color_to_value(pixel, colors, default=0)
        })

    nowcast.sort(key=lambda n: n["datetime"])  # 時刻の古い順

    _cache_nc[(lat, lon, trg)] = (basetime, nowcast)
    return nowcast


def get_rain_next_hour(lat, lon):
    trg = "rain"
    nowcast = get_nowcast(lat, lon, trg)
    return round(sum(n[trg] for n in nowcast) * 5 / 60, 1)


def already_raining(lat, lon):
    nowcast = get_nowcast(lat, lon, "rain")
    if not nowcast:
        return False
    basetime = nowcast[0]["basetime"]
    measured = get_pixel(basetime, basetime, "hrpns", lat, lon, z=NC_ZOOM["rain"], base=BASE_NC)
    return color_to_value(measured, COLOR_DICT_NC, default=0) > 0


def get_thunder_now(lat, lon):
    """現在値(basetime = validtime のタイル)を返す"""
    nowcast = get_nowcast(lat, lon, "thunder")
    if not nowcast:
        return None
    basetime = nowcast[0]["basetime"]
    pixel = get_pixel(basetime, basetime, "thns", lat, lon, z=NC_ZOOM["thunder"], base=BASE_NC)
    return color_to_value(pixel, COLOR_DICT_LNC, default=0)


def get_tornado_now(lat, lon):
    """現在値(basetime = validtime のタイル)を返す"""
    nowcast = get_nowcast(lat, lon, "tornado")
    if not nowcast:
        return None
    basetime = nowcast[0]["basetime"]
    pixel = get_pixel(basetime, basetime, "trns", lat, lon, z=NC_ZOOM["tornado"], base=BASE_NC)
    return color_to_value(pixel, COLOR_DICT_GNC, default=0)


if __name__ == "__main__":
    for item in get_forecast(35.68, 139.77)["hourly"]:
        print(item)
        print(get_rain_next_hour(35.68, 139.77)) 