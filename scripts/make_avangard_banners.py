"""Баннеры бота «Avangard GT» (13.10.2026).

Своего фирменного листа у заказчика нет, поэтому стиль от названия: «GT» — гоночный
гран-туризмо. Графитовый фон с карбоновым плетением, две гоночные полосы цвета
racing red, надписи — SF Pro сверхширокий Black (ось Width 150) с наклоном 12°,
как на ливреях; эмблема — красный шильдик-параллелограмм с «GT».

Запуск: python3 scripts/make_avangard_banners.py  → marat_bot/themes/assets/avangard/*.jpg
"""
from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

GRAPHITE = (17, 19, 22)
CARBON_A = (24, 27, 31)
CARBON_B = (30, 33, 38)
RED = (225, 6, 0)
RED_DARK = (150, 6, 4)
WHITE = (245, 246, 248)
MUTED = (150, 156, 166)
FONT = "/System/Library/Fonts/SFNS.ttf"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "marat_bot", "themes", "assets", "avangard")
W, H = 1280, 720
SS = 3  # суперсэмплинг для гладких краёв
SLANT = 0.21  # наклон ≈ 12°


def font(size: int, weight: int = 900, width: int = 150) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT, size)
    try:
        axes = {a["name"]: a for a in f.get_variation_axes()}
        values = []
        for name in (b"Width", b"Optical Size", b"GRAD", b"Weight"):
            axis = axes.get(name) or axes.get(name.decode())
            if axis is None:
                continue
            values.append({b"Width": width, b"Optical Size": min(96, max(17, size)), b"GRAD": 400,
                           b"Weight": weight}[name])
        f.set_variation_by_axes(values)
    except (OSError, ValueError, KeyError):
        pass
    return f


def slanted_text(base: Image.Image, xy: tuple[float, float], text: str, f: ImageFont.FreeTypeFont,
                 fill: tuple[int, int, int], anchor: str = "l", spacing: float = 0.0) -> float:
    """Текст с наклоном вправо (как на ливрее). anchor — l/m/r по горизонтали, y — базовая линия."""
    probe = ImageDraw.Draw(base)
    widths = [probe.textlength(ch, font=f) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    ascent, descent = f.getmetrics()
    pad = int((ascent + descent) * SLANT) + 8
    layer = Image.new("L", (int(total) + pad * 2, ascent + descent + 8), 0)
    d = ImageDraw.Draw(layer)
    x = pad
    for ch, cw in zip(text, widths):
        d.text((x, ascent + 4), ch, font=f, fill=255, anchor="ls")
        x += cw + spacing
    # сдвиг верха вправо: x' = x + SLANT * (h - y)
    h = layer.height
    layer = layer.transform(layer.size, Image.AFFINE, (1, SLANT, -SLANT * h, 0, 1, 0), resample=Image.BICUBIC)
    x0, y0 = xy
    if anchor == "m":
        x0 -= total / 2
    elif anchor == "r":
        x0 -= total
    base.paste(Image.new("RGB", layer.size, fill), (int(x0 - pad), int(y0 - ascent - 4)), layer)
    return total


def carbon(size: tuple[int, int]) -> Image.Image:
    """Карбоновое плетение: шахматка из коротких диагональных штрихов, очень тихо."""
    w, h = size
    im = Image.new("RGB", size, GRAPHITE)
    d = ImageDraw.Draw(im)
    cell = 14
    for y in range(0, h + cell, cell):
        for x in range(0, w + cell, cell):
            if (x // cell + y // cell) % 2:
                d.polygon([(x, y + cell), (x + cell, y), (x + cell, y + 4), (x + 4, y + cell)], fill=CARBON_A)
            else:
                d.polygon([(x, y), (x + cell, y + cell), (x + cell - 4, y + cell), (x, y + 4)], fill=CARBON_B)
    shade = Image.new("L", size, 0)
    ImageDraw.Draw(shade).rectangle([0, 0, w, h], fill=150)
    return Image.composite(Image.new("RGB", size, GRAPHITE), im, shade)


def stripes(im: Image.Image, x: float, width: float, gap: float, alpha: int = 255) -> None:
    """Две параллельные гоночные полосы через весь кадр по диагонали."""
    w, h = im.size
    mask = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(mask)
    shift = h * SS * 0.55
    for i in range(2):
        left = (x + i * (width + gap)) * SS
        d.polygon([(left + shift, 0), (left + width * SS + shift, 0), (left + width * SS, h * SS), (left, h * SS)],
                  fill=alpha)
    mask = mask.resize((w, h), Image.LANCZOS)
    red = Image.new("RGB", (w, h), RED)
    grad = Image.linear_gradient("L").resize((w, h)).point(lambda v: int(80 + v * 0.7))
    red = Image.composite(red, Image.new("RGB", (w, h), RED_DARK), grad)
    im.paste(red, (0, 0), mask)


def speed_lines(im: Image.Image) -> None:
    d = ImageDraw.Draw(im)
    # только справа внизу — не пересекают заголовок
    for i, (y, length) in enumerate(((520, 300), (566, 180), (612, 260))):
        x = W - 140 - length - i * 30
        d.line([(x, y), (x + length, y)], fill=(70, 74, 82), width=2)


def badge(im: Image.Image, x: int, y: int, height: int) -> int:
    """Красный шильдик-параллелограмм с белым «GT». Возвращает ширину."""
    width = int(height * 2.1)
    skew = int(height * SLANT)
    mask = Image.new("L", ((width + skew) * SS, height * SS), 0)
    ImageDraw.Draw(mask).polygon(
        [(skew * SS, 0), ((width + skew) * SS, 0), (width * SS, height * SS), (0, height * SS)], fill=255)
    mask = mask.resize((width + skew, height), Image.LANCZOS)
    im.paste(Image.new("RGB", mask.size, RED), (x, y), mask)
    slanted_text(im, (x + (width + skew) / 2, y + height * 0.76), "GT", font(int(height * 0.78)), WHITE, anchor="m")
    return width + skew


def signature(im: Image.Image) -> None:
    width = slanted_text(im, (72, H - 52), "AVANGARD", font(30), WHITE, spacing=3)
    badge(im, int(72 + width + 18), H - 80, 34)


def background() -> Image.Image:
    im = carbon((W, H))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([W * 0.55, -H * 0.4, W * 1.3, H * 1.1], fill=70)
    im.paste(Image.new("RGB", (W, H), (60, 12, 10)), (0, 0), glow.filter(ImageFilter.GaussianBlur(170)))
    stripes(im, W * 0.70, 64, 22)
    speed_lines(im)
    return im


def screen(name: str, title: str, subtitle: str, chips: list[str] | None = None) -> None:
    im = background()
    d = ImageDraw.Draw(im)
    d.polygon([(80, 150), (150, 150), (146, 158), (76, 158)], fill=RED)
    lines = title.split("\n")
    size = 76 if max(len(line) for line in lines) <= 11 else 60
    y = 250
    for line in lines:
        slanted_text(im, (72, y), line, font(size), WHITE, spacing=2)
        y += int(size * 1.1)
    sub = font(30, weight=500, width=100)
    y += 12
    for line in subtitle.split("\n"):
        d.text((76, y), line, font=sub, fill=MUTED, anchor="ls")
        y += 42
    if chips:
        x, cy = 74, y + 36
        cf = font(23, weight=700, width=110)
        for chip in chips:
            tw = d.textlength(chip, font=cf)
            d.polygon([(x + 10, cy - 34), (x + tw + 52, cy - 34), (x + tw + 42, cy + 14), (x, cy + 14)],
                      outline=RED, width=2)
            d.text((x + 24, cy - 2), chip, font=cf, fill=WHITE, anchor="ls")
            x += int(tw) + 70
    signature(im)
    im.save(os.path.join(OUT, f"{name}.jpg"), quality=90, optimize=True, progressive=True)


def hero(size: tuple[int, int] = (W, H), tagline: str = "ИНТЕРНЕТ НА ВЫСОКОЙ ПЕРЕДАЧЕ") -> Image.Image:
    w, h = size
    im = carbon(size)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse([w * 0.1, -h * 0.3, w * 0.9, h * 0.9], fill=80)
    im.paste(Image.new("RGB", size, (70, 14, 12)), (0, 0), glow.filter(ImageFilter.GaussianBlur(int(w * 0.12))))
    stripes(im, w * 0.06, w * 0.05, w * 0.017, alpha=90)
    stripes(im, w * 0.80, w * 0.05, w * 0.017, alpha=255)
    word = font(int(h * 0.17))
    slanted_text(im, (w / 2, h * 0.53), "AVANGARD", word, WHITE, anchor="m", spacing=h * 0.006)
    bh = int(h * 0.12)
    bw = int(bh * 2.1) + int(bh * SLANT)
    badge(im, int(w / 2 - bw / 2), int(h * 0.60), bh)
    if tagline:
        d = ImageDraw.Draw(im)
        tf = font(int(h * 0.03), weight=700, width=120)
        d.text((w / 2, h * 0.86), tagline, font=tf, fill=MUTED, anchor="ms")
    return im


def avatar(size: int = 640) -> Image.Image:
    """Аватар: графитовый круг, красные полосы, белое «GT» на шильдике."""
    im = carbon((size, size))
    stripes(im, size * 0.18, size * 0.07, size * 0.03, alpha=255)
    bh = int(size * 0.26)
    bw = int(bh * 2.1) + int(bh * SLANT)
    badge(im, (size - bw) // 2, (size - bh) // 2, bh)
    mask = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * SS - 1, size * SS - 1], fill=255)
    out = Image.new("RGB", (size, size), GRAPHITE)
    out.paste(im, (0, 0), mask.resize((size, size), Image.LANCZOS))
    return out


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    hero().save(os.path.join(OUT, "home.jpg"), quality=90, optimize=True, progressive=True)
    screen("issued", "СТАРТ\nДАН", "Тест-драйв запущен —\nосталось подключить устройство", ["3 дня", "2 устройства", "10 ГБ"])
    screen("connect", "ПОДКЛЮЧЕНИЕ", "Три шага до старта", ["1  Happ", "2  Подписка", "3  Авто-обход"])
    screen("status", "МОЙ\nДОСТУП", "Срок, трафик и ссылка подписки")
    screen("tariffs", "ТАРИФЫ", "Все серверы, Авто-обход\nи до 5 устройств в каждом", ["1 мес", "3 мес", "6 мес", "12 мес"])
    screen("help", "ПОМОЩЬ", "Команды, режимы и что делать,\nесли что-то не работает")
    screen("how", "КАК ЭТО\nРАБОТАЕТ", "Одна ссылка — все серверы сразу", ["Германия", "Нидерланды", "Авто-обход"])
    screen("ref", "ПРИГЛАСИТЬ\nДРУГА", "Поделитесь доступом —\nдругу достанется тест-драйв")
    # Для профиля бота в BotFather: аватар (/setuserpic) и картинка описания (/setdescriptionpic, 640×360).
    avatar().save(os.path.join(OUT, "avatar.png"))
    hero(size=(640, 360), tagline="").save(os.path.join(OUT, "description.jpg"), quality=92)
    print("готово:", ", ".join(sorted(os.listdir(OUT))))


if __name__ == "__main__":
    sys.exit(main())
