import math
from datetime import datetime, timezone
from io import BytesIO

import requests
from PIL import Image
from .const import BASE

# wmタイルの色
COLOR_TO_CONDITION = {
    (255, 170, 0): "sunny",          # 晴
    (170, 170, 170): "cloudy",       # 曇
    (0, 65, 255): "rainy",           # 雨
    (160, 210, 255): "snowy-rainy",  # 雨または雪
    (255, 255, 255): "snowy",        # 雪
}


def parse_time(s):
    # "20261110090000" → UTCの日時
    return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def get_target_times():
    res = requests.get(f"{BASE}/targetTimes.json", timeout=10)
    res.raise_for_status()
    return res.json()


# ---- temperature(geojson) ----
def get_temp_geojson(basetime, validtime):
    url = f"{BASE}/{basetime}/none/{validtime}/surf/temp_point/data.geojson"
    res = requests.get(url, params={"id": "temp_point"}, timeout=30)
    res.raise_for_status()
    return res.json()


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


def get_pixel(basetime, validtime, element, lat, lon, z=8):
    tx, ty, fx, fy = latlon_to_tile(lat, lon, z)
    url = f"{BASE}/{basetime}/none/{validtime}/surf/{element}/{z}/{tx}/{ty}.png"
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    img = Image.open(BytesIO(res.content)).convert("RGBA")
    return img.getpixel((int(fx * img.width), int(fy * img.height)))


def color_to_condition(rgba):
    r, g, b, a = rgba
    if a == 0:
        return None
    nearest = min(
        COLOR_TO_CONDITION,
        key=lambda c: (c[0] - r) ** 2 + (c[1] - g) ** 2 + (c[2] - b) ** 2,
    )
    return COLOR_TO_CONDITION[nearest]


# ---- まとめ ----
def get_forecast(lat, lon):
    forecast = []
    for t in get_target_times():
        if "wm" not in t["elements"] or "temp_point" not in t["elements"]:
            continue
        pixel = get_pixel(t["basetime"], t["validtime"], "wm", lat, lon)
        geo = get_temp_geojson(t["basetime"], t["validtime"])
        forecast.append({
            "datetime": parse_time(t["validtime"]).isoformat(),
            "condition": color_to_condition(pixel),
            "temperature": nearest_temp(geo, lat, lon),
        })
    return forecast


if __name__ == "__main__":
    for item in get_forecast(35.68, 139.77):
        print(item)