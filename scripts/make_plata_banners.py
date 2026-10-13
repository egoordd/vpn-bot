"""Баннеры бота «Plata VPN» (бывший «Ярослав VPN») по логотипу заказчика (13.10.2026).

Светлая тема: кремовый фон #FEF8EC, тёмно-синий #172854, янтарный шеврон
#F5C561 → #F2A54D. Щит с шевроном рисуется векторно по пропорциям логотипа
(205×232: скат крыши сверху, прямые бока, плавный низ к острию), надписи —
SF Pro Rounded (системный округлый шрифт, близкий к начертанию «Plata»).

Запуск: python3 scripts/make_plata_banners.py  → marat_bot/themes/assets/plata/*.jpg
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_etalon_banners import font, spaced  # noqa: E402  — общие шрифт и разрядка

CREAM = (254, 248, 236)
WARM = (252, 236, 210)
NAVY = (23, 40, 84)
AMBER_TOP = (247, 200, 102)
AMBER_BOTTOM = (242, 164, 72)
MUTED = (96, 106, 135)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "marat_bot", "themes", "assets", "plata")
W, H = 1280, 720
SS = 4


def _bezier(p0, p1, p2, p3, steps=40):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t ** 2, t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def _fillet(points: list[tuple[float, float]], corners: dict[int, float], steps: int = 12) -> list[tuple[float, float]]:
    """Скруглить вершины многоугольника: вершина i заменяется дугой радиуса corners[i]."""
    out: list[tuple[float, float]] = []
    n = len(points)
    for i, (x, y) in enumerate(points):
        r = corners.get(i)
        if not r:
            out.append((x, y))
            continue
        (px, py), (nx, ny) = points[i - 1], points[(i + 1) % n]
        d1, d2 = ((px - x) ** 2 + (py - y) ** 2) ** 0.5, ((nx - x) ** 2 + (ny - y) ** 2) ** 0.5
        a = (x + (px - x) * min(r / d1, 0.5), y + (py - y) * min(r / d1, 0.5))
        b = (x + (nx - x) * min(r / d2, 0.5), y + (ny - y) * min(r / d2, 0.5))
        for k in range(steps + 1):
            t = k / steps
            out.append(((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * x + t ** 2 * b[0],
                        (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * y + t ** 2 * b[1]))
    return out


def logo(height: int) -> Image.Image:
    """Щит с шевроном (RGBA), высота height. Единицы — пиксели логотипа 205×232."""
    u = height * SS / 232.0
    w = int(205 * u) + 2
    hh = int(232 * u) + 2

    def p(x, y):
        return (x * u + 1, y * u + 1)

    curve = _bezier((0, 118), (0, 178), (58, 220), (102.5, 232))
    outline = [(102.5, 0), (205, 36), (205, 118)] + [(205 - x, y) for x, y in curve[1:]]
    tip = len(outline) - 1
    outline += [(x, y) for x, y in reversed(curve[:-1])] + [(0, 36)]
    shield_pts = _fillet(outline, {0: 16, 1: 16, tip: 10, len(outline) - 1: 16})
    shield = Image.new("L", (w, hh), 0)
    ImageDraw.Draw(shield).polygon([p(x, y) for x, y in shield_pts], fill=255)
    chev = [(22, 140), (104, 70), (181, 138), (177, 148), (143, 148), (104, 104), (37, 154)]
    chev_pts = _fillet(chev, {0: 9, 1: 14, 2: 5, 3: 5, 4: 8, 5: 6, 6: 9})
    chevron = Image.new("L", (w, hh), 0)
    ImageDraw.Draw(chevron).polygon([p(x, y) for x, y in chev_pts], fill=255)
    grad = Image.new("RGB", (w, hh))
    gd = ImageDraw.Draw(grad)
    for y in range(hh):
        t = min(1, max(0, (y / u - 72) / 76))
        gd.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(AMBER_TOP, AMBER_BOTTOM)))
    im = Image.new("RGBA", (w, hh), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (w, hh), NAVY + (255,)), (0, 0), shield)
    im.paste(grad, (0, 0), chevron)
    return im.resize((w // SS, hh // SS), Image.LANCZOS)


def wordmark(draw: ImageDraw.ImageDraw, xy, size: int, anchor: str = "l") -> float:
    return spaced(draw, xy, "Plata", font(size, "Semibold"), NAVY, size * 0.01, anchor=anchor)


def background() -> Image.Image:
    im = Image.new("RGB", (W, H), CREAM)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.55, -H * 0.2, W * 1.2, H * 1.1], fill=170)
    im.paste(Image.new("RGB", (W, H), WARM), (0, 0), glow.filter(ImageFilter.GaussianBlur(150)))
    dots = ImageDraw.Draw(im)
    for gx in range(0, 7):
        for gy in range(0, 4):
            x, y = 76 + gx * 22, 70 + gy * 22
            dots.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(236, 220, 192))
    return im


def signature(im: Image.Image) -> None:
    mark = logo(44)
    im.paste(mark, (72, H - 100), mark)
    wordmark(ImageDraw.Draw(im), (72 + mark.width + 14, H - 64), 34)


def screen(name: str, title: str, subtitle: str, chips: list[str] | None = None) -> None:
    im = background()
    d = ImageDraw.Draw(im)
    mark = logo(400)
    im.paste(mark, (W - mark.width - 110, (H - mark.height) // 2), mark)
    d.rounded_rectangle([72, 176, 72 + 56, 176 + 8], radius=4, fill=AMBER_BOTTOM)
    y = 270
    for line in title.split("\n"):
        d.text((70, y), line, font=font(70, "Bold"), fill=NAVY, anchor="ls")
        y += 80
    y += 8
    for line in subtitle.split("\n"):
        d.text((72, y), line, font=font(30, "Medium"), fill=MUTED, anchor="ls")
        y += 42
    if chips:
        x, cy = 72, y + 36
        cf = font(24, "Semibold")
        for chip in chips:
            tw = d.textlength(chip, font=cf)
            d.rounded_rectangle([x, cy - 34, x + tw + 56, cy + 14], radius=24, fill=(255, 255, 255), outline=(238, 222, 196), width=2)
            d.ellipse([x + 18, cy - 15, x + 28, cy - 5], fill=AMBER_BOTTOM)
            d.text((x + 38, cy - 2), chip, font=cf, fill=NAVY, anchor="ls")
            x += tw + 70
    signature(im)
    im.save(os.path.join(OUT, f"{name}.jpg"), quality=90, optimize=True, progressive=True)


def hero(size=(W, H), tagline: str | None = "Безопасный и быстрый интернет") -> Image.Image:
    w, h = size
    im = Image.new("RGB", size, CREAM)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse([w * 0.2, h * 0.05, w * 0.8, h * 0.95], fill=150)
    im.paste(Image.new("RGB", size, WARM), (0, 0), glow.filter(ImageFilter.GaussianBlur(int(w * 0.1))))
    d = ImageDraw.Draw(im)
    mark = logo(int(h * 0.34))
    word_size = int(h * 0.2)
    word_w = d.textlength("Plata", font=font(word_size, "Semibold")) + word_size * 0.04
    gap = int(h * 0.06)
    x0 = int((w - (mark.width + gap + word_w)) / 2)
    top = int(h * 0.30) if tagline else int((h - mark.height) / 2)
    im.paste(mark, (x0, top), mark)
    wordmark(d, (x0 + mark.width + gap, top + mark.height * 0.76), word_size)
    if tagline:
        d.text((w / 2, h * 0.80), tagline, font=font(int(h * 0.042), "Medium"), fill=MUTED, anchor="ms")
    return im


def avatar(size: int = 640) -> Image.Image:
    im = Image.new("RGB", (size, size), CREAM)
    mark = logo(int(size * 0.56))
    im.paste(mark, ((size - mark.width) // 2, (size - mark.height) // 2 + int(size * 0.01)), mark)
    return im


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    hero().save(os.path.join(OUT, "home.jpg"), quality=90, optimize=True, progressive=True)
    screen("issued", "Доступ открыт", "Пробный период запущен —\nосталось подключить устройство", ["3 дня", "2 устройства", "10 ГБ"])
    screen("connect", "Подключение", "Три шага — меньше минуты", ["Happ", "Подписка", "Авто-обход"])
    screen("status", "Мой доступ", "Срок, трафик и ссылка подписки")
    screen("tariffs", "Тарифы", "Все страны, Авто-обход\nи до 5 устройств в каждом", ["1 мес", "3 мес", "6 мес", "12 мес"])
    screen("help", "Помощь", "Команды, режимы и что делать,\nесли что-то не работает")
    screen("how", "Как это\nработает", "Одна ссылка — все страны и режимы", ["Польша", "Финляндия", "Нидерланды", "США"])
    screen("ref", "Пригласить\nдруга", "Поделитесь доступом —\nдругу достанется пробный период")
    avatar().save(os.path.join(OUT, "avatar.png"))
    hero(size=(640, 360), tagline=None).save(os.path.join(OUT, "description.jpg"), quality=92)
    print("готово:", ", ".join(sorted(os.listdir(OUT))))


if __name__ == "__main__":
    sys.exit(main())
