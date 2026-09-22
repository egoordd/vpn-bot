"""Переписать надпись на плашке баннера, не трогая остальное (нужен Chrome на Mac).

Цифры на баннерах зеркала (срок пробника, ГБ) нарисованы в самой картинке, а
исходников у картинок нет. 22.09.2026 так «7 дней» вернули в «3 дня».

    .venv/bin/python scripts/rewrite_banner_chip.py '{"src": "assets/mirror/banner_cabinet.png",
        "chip": [645, 404, 912, 448], "old": "7 дней бесплатно", "new": "3 дня бесплатно",
        "families": ["system-ui"], "weights": [650, 700], "sizes": [25.5, 26, 26.5],
        "dys": [-4, -3, -2, -1]}'

chip — область поиска текста внутри плашки (x0, y0, x1, y1). Результат —
<имя>_new.png рядом со скриптом во временной папке; проверьте глазами и
скопируйте на место. Для плашек зеркала подходит system-ui 650–700, ~26 px.

1. Стираем старый текст внутри плашки: каждая строка плашки заполняется
   линейной интерполяцией между её цветом слева и справа от текста — фон
   плашки плавный, так рамка и градиент остаются нетронутыми.
2. Подбираем шрифт/размер/сдвиг: рисуем в Chrome СТАРЫЙ текст на стёртой
   плашке и сравниваем с оригиналом по пикселям.
3. Тем же набором параметров рисуем новый текст.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(tempfile.gettempdir()) / "rewrite_banner_chip"
HERE.mkdir(exist_ok=True)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H = 1200, 630


def find_text_box(im, box, thresh=150):
    """Рамка светлых пикселей текста внутри области плашки."""
    x0, y0, x1, y1 = box
    xs, ys = [], []
    px = im.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y][:3]
            if min(r, g, b) > thresh:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def clean_chip(im, text_box, pad=6):
    """Стереть текст: интерполяция по строкам между краями вне текста."""
    out = im.copy()
    px = out.load()
    tx0, ty0, tx1, ty1 = text_box
    xl, xr = tx0 - pad, tx1 + pad
    for y in range(ty0 - pad, ty1 + pad):
        left = px[xl, y]
        right = px[xr, y]
        for x in range(xl + 1, xr):
            t = (x - xl) / (xr - xl)
            px[x, y] = tuple(round(left[i] * (1 - t) + right[i] * t) for i in range(3))
    return out


def render(cleaned_path, variants, out_png):
    """Один скриншот: все варианты друг под другом, по 630 px каждый."""
    blocks = []
    for i, v in enumerate(variants):
        blocks.append(
            f'<div style="position:absolute;left:0;top:{i * H}px;width:{W}px;height:{H}px;'
            f'background:url(file://{cleaned_path}) no-repeat;">'
            f'<span style="position:absolute;left:{v["cx"]}px;top:{v["cy"]}px;'
            f'transform:translate(-50%,-50%);white-space:nowrap;font-family:{v["family"]};'
            f'font-weight:{v["weight"]};font-size:{v["size"]}px;letter-spacing:{v["ls"]}px;'
            f'color:{v["color"]};-webkit-font-smoothing:antialiased;line-height:1">{v["text"]}</span></div>'
        )
    html = (
        "<!doctype html><html><head><meta charset='utf-8'><style>html,body{margin:0;padding:0;"
        f"width:{W}px;height:{H * len(variants)}px;overflow:hidden;background:#000}}</style></head>"
        f"<body>{''.join(blocks)}</body></html>"
    )
    page = Path(tempfile.mkdtemp(dir=HERE)) / "page.html"
    page.write_text(html)
    profile = tempfile.mkdtemp(dir=HERE)
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={profile}",
         "--force-device-scale-factor=1", f"--window-size={W},{H * len(variants)}",
         "--allow-file-access-from-files", f"--screenshot={out_png}", f"file://{page}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Headless Chrome часто не выходит сам после снимка: ждём файл, потом гасим.
    import time
    out = Path(out_png)
    out.unlink(missing_ok=True)
    deadline = time.time() + 60
    last = -1
    while time.time() < deadline:
        if out.exists() and out.stat().st_size > 0 and out.stat().st_size == last:
            break
        last = out.stat().st_size if out.exists() else -1
        time.sleep(0.5)
    proc.kill()
    return Image.open(out_png).convert("RGB")


def score(shot, i, original, box):
    tile = shot.crop((0, i * H, W, (i + 1) * H)).crop(box)
    diff = ImageChops.difference(tile, original.crop(box))
    return sum(ImageStat.Stat(diff).mean) / 3


def main():
    spec = json.loads(sys.argv[1])
    src = Path(spec["src"])
    original = Image.open(src).convert("RGB")
    text_box = find_text_box(original, spec["chip"])
    print("text box", text_box)
    cleaned = clean_chip(original, text_box)
    cleaned_path = HERE / (src.stem + "_clean.png")
    cleaned.save(cleaned_path)

    cx = (text_box[0] + text_box[2]) / 2
    cy = (text_box[1] + text_box[3]) / 2
    # Цвет текста — средний из самых светлых пикселей исходной надписи.
    px = original.load()
    bright = [px[x, y] for y in range(text_box[1], text_box[3]) for x in range(text_box[0], text_box[2])
              if min(px[x, y]) > 215]
    avg = tuple(round(sum(c[i] for c in bright) / len(bright)) for i in range(3))
    color = spec.get("color") or "#%02x%02x%02x" % avg
    print("text color", color)
    families = spec.get("families", ["-apple-system", "'Helvetica Neue'", "'SF Pro Text'"])
    variants = []
    for family in families:
        for weight in spec.get("weights", (600, 700)):
            for size in spec.get("sizes", (26, 27, 28, 29, 30)):
                for dy in spec.get("dys", (-1, 0, 1, 2)):
                    variants.append({"family": family, "weight": weight, "size": size, "ls": 0,
                                     "cx": cx, "cy": cy + dy, "color": color, "text": spec["old"]})
    score_box = (text_box[0] - 8, text_box[1] - 6, text_box[2] + 8, text_box[3] + 6)
    # Chrome не снимает страницы выше ~16 000 px: считаем порциями по 20 вариантов.
    scored = []
    for start in range(0, len(variants), 20):
        chunk = variants[start:start + 20]
        shot = render(cleaned_path, chunk, HERE / (src.stem + f"_calib_{start}.png"))
        scored += [(score(shot, i, original, score_box), v) for i, v in enumerate(chunk)]
    ranked = sorted(scored, key=lambda t: t[0])
    for s, v in ranked[:4]:
        print(f"{s:6.2f}", v["family"], v["weight"], v["size"], "dy", v["cy"] - cy)
    best = ranked[0][1]

    final = dict(best, text=spec["new"])
    out = render(cleaned_path, [final], HERE / (src.stem + "_new_raw.png"))
    out.save(HERE / (src.stem + "_new.png"))
    print("saved", HERE / (src.stem + "_new.png"))


if __name__ == "__main__":
    main()
