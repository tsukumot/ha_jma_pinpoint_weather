import sys
import types
from pathlib import Path

# 「jma」という名前の空のパッケージを自作して、中身はこのフォルダだと教える
pkg = types.ModuleType("jma")
pkg.__path__ = [str(Path(__file__).parent)]
sys.modules["jma"] = pkg  # 「jmaパッケージがある」と登録する

from jma.forecast import get_forecast, get_rain_next_hour, get_nc_times

lat = 33.949341
lon = 131.111526
print(get_rain_next_hour(lat, lon))
result = get_forecast(lat, lon)
print(result["hourly"][:3])