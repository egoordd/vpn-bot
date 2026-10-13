"""Баннеры бота «Etalon VPN» по фирменному листу (13.10.2026).

Тёмно-синий #0F1A33, золото #D4B06A, слоновая кость #F4ECDD; ключ-«E» рисуется
векторно по пропорциям логотипа (кольцо, стержень, три зубца со скруглёнными
концами), надписи — SF Pro Rounded Bold (системный шрифт macOS, близкий к
M PLUS Rounded 1c из листа), прописными с разрядкой.

Запуск: python3 scripts/make_etalon_banners.py  → marat_bot/themes/assets/etalon/*.jpg
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

NAVY = (15, 26, 51)
NAVY_LIGHT = (27, 43, 78)
GOLD = (212, 176, 106)
IVORY = (244, 236, 221)
MUTED = (150, 160, 184)
FONT = "/System/Library/Fonts/SFNSRounded.ttf"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "marat_bot", "themes", "assets", "etalon")
W, H = 1280, 720
SS = 3  # суперсэмплинг для гладких краёв


def font(size: int, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass
    return f


def key_mask(height: int) -> Image.Image:
    """Ключ-«E» (маска, белое — ключ). Пропорции сняты с логотипа: высота 530 единиц."""
    u = height / 530.0
    w = int(260 * u) + 4
    im = Image.new("L", (w * SS, height * SS + 4), 0)
    d = ImageDraw.Draw(im)
    s = u * SS
    cx, cy = 107 * s, 107 * s
    d.ellipse([cx - 107 * s, cy - 107 * s, cx + 107 * s, cy + 107 * s], fill=255)
    d.ellipse([cx - 57 * s, cy - 57 * s, cx + 57 * s, cy + 57 * s], fill=0)
    x0, x1 = cx - 24.5 * s, cx + 24.5 * s
    d.rounded_rectangle([x0, cy + 90 * s, x1, cy + 423 * s], radius=int(24 * s), fill=255)
    d.rectangle([x0 + 24 * s, cy + 90 * s, x1, cy + 423 * s], fill=255)
    for yc, length in ((214, 145), (308, 106), (399, 145)):
        d.rounded_rectangle([x0, cy + (yc - 24) * s, cx + length * s, cy + (yc + 24) * s], radius=int(24 * s), fill=255)
    return im.resize((w, height + 1), Image.LANCZOS)


def paste_key(base: Image.Image, x: int, y: int, height: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    mask = key_mask(height)
    if alpha < 1:
        mask = mask.point(lambda v: int(v * alpha))
    base.paste(Image.new("RGB", mask.size, color), (x, y), mask)


def spaced(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, f: ImageFont.FreeTypeFont,
           fill, spacing: float, anchor: str = "l") -> float:
    """Текст с разрядкой; anchor l/m/r по горизонтали. Возвращает ширину."""
    widths = [draw.textlength(ch, font=f) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x, y = xy
    if anchor == "m":
        x -= total / 2
    elif anchor == "r":
        x -= total
    for ch, cw in zip(text, widths):
        draw.text((x, y), ch, font=f, fill=fill, anchor="ls")
        x += cw + spacing
    return total


def background() -> Image.Image:
    """Тёмно-синий фон с мягким светом справа и тонкими золотыми дугами — глубина без шума."""
    im = Image.new("RGB", (W, H), NAVY)
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.45, -H * 0.35, W * 1.35, H * 1.15], fill=120)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    im.paste(Image.new("RGB", (W, H), NAVY_LIGHT), (0, 0), glow)
    arcs = Image.new("L", (W * SS, H * SS), 0)
    ad = ImageDraw.Draw(arcs)
    cx, cy = int(W * 0.80 * SS), int(H * 0.50 * SS)
    for i, r in enumerate((300, 420, 540, 660)):
        rr = r * SS
        ad.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=34 - i * 6, width=2 * SS)
    arcs = arcs.resize((W, H), Image.LANCZOS)
    im.paste(Image.new("RGB", (W, H), GOLD), (0, 0), arcs)
    return im


def signature(im: Image.Image) -> None:
    d = ImageDraw.Draw(im)
    paste_key(im, 72, H - 104, 46, GOLD)
    spaced(d, (112, H - 70), "ETALON", font(26), GOLD, 7)
    spaced(d, (114, H - 46), "VPN", font(14, "Semibold"), IVORY, 6)


def screen(name: str, title: str, subtitle: str, chips: list[str] | None = None) -> None:
    im = background()
    d = ImageDraw.Draw(im)
    paste_key(im, W - 330, 150, 420, GOLD)
    d.rounded_rectangle([72, 150, 72 + 64, 150 + 6], radius=3, fill=GOLD)
    lines = title.split("\n")
    size = 72 if max(len(line) for line in lines) <= 14 else 58
    y = 250
    for line in lines:
        spaced(d, (72, y), line, font(size), IVORY, size * 0.06)
        y += int(size * 1.12)
    sub = font(30, "Medium")
    y += 10
    for line in subtitle.split("\n"):
        d.text((74, y), line, font=sub, fill=MUTED, anchor="ls")
        y += 42
    if chips:
        x, cy = 72, y + 34
        cf = font(24, "Semibold")
        for chip in chips:
            tw = d.textlength(chip, font=cf)
            d.rounded_rectangle([x, cy - 34, x + tw + 44, cy + 14], radius=24, outline=GOLD, width=2)
            d.text((x + 22, cy - 2), chip, font=cf, fill=GOLD, anchor="ls")
            x += tw + 60
    signature(im)
    im.save(os.path.join(OUT, f"{name}.jpg"), quality=90, optimize=True, progressive=True)


def hero(name: str = "home", size: tuple[int, int] = (W, H), tagline: str = "ЭТАЛОН СВОБОДНОГО ИНТЕРНЕТА") -> Image.Image:
    w, h = size
    im = Image.new("RGB", size, NAVY)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse([w * 0.18, -h * 0.25, w * 0.82, h * 0.95], fill=110)
    im.paste(Image.new("RGB", size, NAVY_LIGHT), (0, 0), glow.filter(ImageFilter.GaussianBlur(int(w * 0.12))))
    d = ImageDraw.Draw(im)
    kh = int(h * 0.36)
    kw = key_mask(kh).width
    paste_key(im, (w - kw) // 2, int(h * 0.12), kh, GOLD)
    spaced(d, (w / 2, h * 0.68), "ETALON", font(int(h * 0.115)), GOLD, h * 0.035, anchor="m")
    spaced(d, (w / 2, h * 0.775), "VPN", font(int(h * 0.04), "Semibold"), IVORY, h * 0.03, anchor="m")
    if tagline:
        spaced(d, (w / 2, h * 0.895), tagline, font(int(h * 0.028), "Semibold"), MUTED, h * 0.006, anchor="m")
    return im


def avatar(size: int = 640) -> Image.Image:
    """Аватар из листа: золотой круг, тёмно-синий ключ."""
    big = size * SS
    im = Image.new("RGB", (big, big), NAVY)
    ImageDraw.Draw(im).ellipse([0, 0, big - 1, big - 1], fill=GOLD)
    im = im.resize((size, size), Image.LANCZOS)
    kh = int(size * 0.52)
    kw = key_mask(kh).width
    paste_key(im, (size - kw) // 2, (size - kh) // 2, kh, NAVY)
    return im


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    hero().save(os.path.join(OUT, "home.jpg"), quality=90, optimize=True, progressive=True)
    screen("issued", "ДОСТУП\nОТКРЫТ", "Пробный период запущен —\nосталось подключить устройство", ["3 дня", "2 устройства", "10 ГБ"])
    screen("connect", "ПОДКЛЮЧЕНИЕ", "Три шага — меньше минуты", ["1  Happ", "2  Подписка", "3  Авто-обход"])
    screen("status", "МОЙ ДОСТУП", "Срок, трафик и ссылка подписки")
    screen("tariffs", "ТАРИФЫ", "Все страны, Авто-обход\nи до 5 устройств в каждом", ["1 мес", "3 мес", "6 мес", "12 мес"])
    screen("help", "ПОМОЩЬ", "Команды, режимы и что делать,\nесли что-то не работает")
    screen("how", "КАК ЭТО\nРАБОТАЕТ", "Одна ссылка — все страны и режимы", ["Польша", "Финляндия", "Нидерланды", "США"])
    screen("ref", "ПРИГЛАСИТЬ\nДРУГА", "Поделитесь доступом —\nдругу достанется пробный период")
    # Для профиля бота в BotFather: аватар (/setuserpic) и картинка описания (/setdescriptionpic, 640×360).
    avatar().save(os.path.join(OUT, "avatar.png"))
    hero(size=(640, 360), tagline="").save(os.path.join(OUT, "description.jpg"), quality=92)
    print("готово:", ", ".join(sorted(os.listdir(OUT))))


if __name__ == "__main__":
    sys.exit(main())
