import math
from datetime import datetime

import requests

from .const import AMEDAS_LATEST_URL, AMEDAS_MAP_URL, AMEDAS_TABLE_URL

_table = None  # 観測所一覧。ほぼ変わらないので1回だけ取って使い回す


def get_table():
    global _table  # 関数の外の変数 _table を書き換えるために必要
    if _table is None:
        res = requests.get(AMEDAS_TABLE_URL, timeout=10)
        res.raise_for_status()
        _table = res.json()
    return _table


def get_latest_map():
    # latest_time.txt は "2026-11-11T12:30:00+09:00" 形式 → URL用の "20261111123000" に直す
    res = requests.get(AMEDAS_LATEST_URL, timeout=10)
    res.raise_for_status()
    observed_at = res.text.strip()
    ts = datetime.fromisoformat(observed_at).strftime("%Y%m%d%H%M%S")

    res = requests.get(AMEDAS_MAP_URL.format(ts=ts), timeout=30)
    res.raise_for_status()
    return observed_at, res.json()


def nearest_station(data, key, lat, lon):
    """data の中で key を持つ、一番近い観測所の id と名前を返す"""
    table = get_table()
    best = None
    best_dist = None
    for sid, obs in data.items():
        if key not in obs or obs[key][0] is None or sid not in table:
            continue
        st = table[sid]
        slat = st["lat"][0] + st["lat"][1] / 60
        slon = st["lon"][0] + st["lon"][1] / 60
        dx = (slon - lon) * math.cos(math.radians(lat))
        dist = dx ** 2 + (slat - lat) ** 2
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = {"id": sid, "name": st["kjName"]}
    return best

def get_amedas(lat, lon):
    observed_at, data = get_latest_map()
    result = {"observed_at": observed_at}
    # グループ名: 最寄りを探すときの基準にする項目
    for group, key in (("temp", "temp"), ("precip", "precipitation1h")):
        st = nearest_station(data, key, lat, lon)
        if st:
            # その観測所の全項目を {項目名: 値} にする([値, 品質情報] の先頭が値)
            st["values"] = {
                k: v[0] for k, v in data[st["id"]].items()
                if isinstance(v, list) and v
            }
        result[group] = st  # 見つからなければ None
    return result