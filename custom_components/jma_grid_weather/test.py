from collections import Counter
from io import BytesIO
import requests
from PIL import Image

url = "https://www.jma.go.jp/bosai/jmatile/data/wdist/20261110080000/none/20261110120000/surf/wm/8/225/99.png"

res = requests.get(url, timeout=10)
res.raise_for_status()
img = Image.open(BytesIO(res.content)).convert("RGBA")

print(img.size)                                   # タイルの大きさ(256×256のはず)
for color, count in Counter(img.getdata()).most_common(10):
    print(color, count)                           # (R,G,B,A) と、その色の画素数