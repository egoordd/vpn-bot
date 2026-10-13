"""Баннеры бота «Avangard GT» (13.10.2026).

Своего фирменного листа у заказчика нет, поэтому стиль от названия: «GT» — гоночный
гран-туризмо. Графитовый фон с карбоновым плетением, две гоночные полосы цвета
racing red, надписи — SF Pro сверхширокий Black (ось Width 150) с наклоном 12°,
как на ливреях; эмблема — красный шильдик-параллелограмм с «GT».

Запуск: python3 scripts/make_avangard_banners.py  → marat_bot/themes/assets/avangard/*.jpg
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

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


HIRAGINO = "/System/Library/Fonts/Hiragino Sans GB.ttc"
SWIFT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "render_text.swift")


def _swift_renderer() -> str:
    """Собрать (один раз) утилиту CoreText — ею рисуются надписи на фарси."""
    binary = os.path.join(tempfile.gettempdir(), "avangard_render_text")
    if not os.path.exists(binary) or os.path.getmtime(binary) < os.path.getmtime(SWIFT_SRC):
        subprocess.run(["swiftc", "-O", SWIFT_SRC, "-o", binary], check=True)
    return binary


def text_layer(text: str, size: int, lang: str, weight: int = 900, width: int = 150,
               color: tuple[int, int, int] = WHITE) -> Image.Image:
    """Строка текста на прозрачном слое. Латиница/кириллица — SF Pro сверхширокий, китайский —
    Hiragino Sans GB, фарси — системный шрифт через CoreText (PIL без raqm его не соединяет)."""
    if lang == "fa":
        names = {500: "medium", 700: "bold", 900: "black"}
        out = os.path.join(tempfile.gettempdir(), f"avg_fa_{abs(hash((text, size, weight, color)))}.png")
        hexcolor = "#%02X%02X%02X" % color
        subprocess.run([_swift_renderer(), text, str(size), names.get(weight, "bold"), hexcolor, out], check=True)
        return Image.open(out).convert("RGBA")
    if lang == "zh":
        f = ImageFont.truetype(HIRAGINO, size, index=1 if weight >= 600 else 0)
    else:
        f = font(size, weight=weight, width=width)
    left, top, right, bottom = f.getbbox(text)
    layer = Image.new("RGBA", (right - left + 12, bottom - top + 12), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((6 - left, 6 - top), text, font=f, fill=color + (255,))
    return layer


def slant(layer: Image.Image) -> Image.Image:
    """Наклон вправо, как на ливрее (фарси не наклоняем — справа налево он выглядел бы падающим)."""
    pad = int(layer.height * SLANT) + 2
    wide = Image.new("RGBA", (layer.width + pad, layer.height), (0, 0, 0, 0))
    wide.paste(layer, (0, 0))
    return wide.transform(wide.size, Image.AFFINE, (1, SLANT, -SLANT * layer.height, 0, 1, 0), resample=Image.BICUBIC)


def screen(out_dir: str, lang: str, name: str, title: str, subtitle: str, chips: list[str] | None = None) -> None:
    im = background().convert("RGBA")
    d = ImageDraw.Draw(im)
    d.polygon([(80, 150), (150, 150), (146, 158), (76, 158)], fill=RED)
    lines = title.split("\n")
    size = 76 if max(len(line) for line in lines) <= 11 else 60
    if lang == "zh":
        size = 84
    y = 190
    for line in lines:
        layer = text_layer(line, size, lang)
        layer = layer if lang == "fa" else slant(layer)
        im.alpha_composite(layer, (66, y))
        y += int(layer.height * 1.02)
    y += 18
    for line in subtitle.split("\n"):
        layer = text_layer(line, 30, lang, weight=500, width=100, color=MUTED)
        im.alpha_composite(layer, (70, y))
        y += 44
    if chips:
        x, top = 74, y + 14
        for chip in chips:
            layer = text_layer(chip, 23, lang, weight=700, width=110)
            w, h = layer.width + 30, 48
            d.polygon([(x + 10, top), (x + w + 10, top), (x + w, top + h), (x, top + h)], outline=RED, width=2)
            im.alpha_composite(layer, (x + 14, top + (h - layer.height) // 2))
            x += w + 26
    signature(im)
    im.convert("RGB").save(os.path.join(out_dir, f"{name}.jpg"), quality=90, optimize=True, progressive=True)


def hero(size: tuple[int, int] = (W, H), tagline: str = "", lang: str = "ru") -> Image.Image:
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
        rgba = im.convert("RGBA")
        layer = text_layer(tagline, int(h * 0.032), lang, weight=700, width=120, color=MUTED)
        rgba.alpha_composite(layer, (int(w / 2 - layer.width / 2), int(h * 0.83)))
        im = rgba.convert("RGB")
    return im


# Надписи баннеров на языках интерфейса: слоган главной и (заголовок, подпись, чипы) экранов.
BANNER_TEXTS = {
    "ru": ("ИНТЕРНЕТ НА ВЫСОКОЙ ПЕРЕДАЧЕ", {
        "issued": ("СТАРТ\nДАН", "Тест-драйв запущен —\nосталось подключить устройство", ["3 дня", "2 устройства", "10 ГБ"]),
        "connect": ("ПОДКЛЮЧЕНИЕ", "Три шага до старта", ["1  Happ", "2  Подписка", "3  Авто-обход"]),
        "status": ("МОЙ\nДОСТУП", "Срок, трафик и ссылка подписки", None),
        "tariffs": ("ТАРИФЫ", "Все серверы, Авто-обход\nи до 5 устройств в каждом", ["1 мес", "3 мес", "6 мес", "12 мес"]),
        "help": ("ПОМОЩЬ", "Команды, режимы и что делать,\nесли что-то не работает", None),
        "how": ("КАК ЭТО\nРАБОТАЕТ", "Одна ссылка — все серверы сразу", ["Польша", "Финляндия", "Нидерланды", "США"]),
        "ref": ("ПРИГЛАСИТЬ\nДРУГА", "Поделитесь доступом —\nдругу достанется тест-драйв", None),
    }),
    "en": ("INTERNET IN HIGH GEAR", {
        "issued": ("YOU'RE\nOFF", "Test drive started —\nnow connect a device", ["3 days", "2 devices", "10 GB"]),
        "connect": ("CONNECT", "Three steps to start", ["1  Happ", "2  Subscription", "3  Auto mode"]),
        "status": ("MY\nACCESS", "Term, traffic and subscription link", None),
        "tariffs": ("PLANS", "All servers, Auto mode\nand up to 5 devices in each", ["1 mo", "3 mo", "6 mo", "12 mo"]),
        "help": ("HELP", "Commands, modes and what to do\nif something stops working", None),
        "how": ("HOW IT\nWORKS", "One link — every server at once", ["Poland", "Finland", "Netherlands", "USA"]),
        "ref": ("INVITE A\nFRIEND", "Share access —\nyour friend gets a test drive", None),
    }),
    "uk": ("ІНТЕРНЕТ НА ВИСОКІЙ ПЕРЕДАЧІ", {
        "issued": ("СТАРТ\nДАНО", "Тест-драйв запущено —\nзалишилося підключити пристрій", ["3 дні", "2 пристрої", "10 ГБ"]),
        "connect": ("ПІДКЛЮЧЕННЯ", "Три кроки до старту", ["1  Happ", "2  Підписка", "3  Авто-режим"]),
        "status": ("МІЙ\nДОСТУП", "Термін, трафік і посилання підписки", None),
        "tariffs": ("ТАРИФИ", "Усі сервери, Авто-режим\nі до 5 пристроїв у кожному", ["1 міс", "3 міс", "6 міс", "12 міс"]),
        "help": ("ДОПОМОГА", "Команди, режими і що робити,\nякщо щось не працює", None),
        "how": ("ЯК ЦЕ\nПРАЦЮЄ", "Одне посилання — усі сервери одразу", ["Польща", "Фінляндія", "Нідерланди", "США"]),
        "ref": ("ЗАПРОСИТИ\nДРУГА", "Поділіться доступом —\nдруг отримає тест-драйв", None),
    }),
    "zh": ("高速档位的互联网", {
        "issued": ("出发！", "试驾已开始——\n现在连接设备", ["3 天", "2 台设备", "10 GB"]),
        "connect": ("连接设备", "三步即可开始", ["1  Happ", "2  订阅", "3  自动模式"]),
        "status": ("我的访问", "期限、流量和订阅链接", None),
        "tariffs": ("套餐", "所有服务器、自动模式\n每个套餐最多 5 台设备", ["1 个月", "3 个月", "6 个月", "12 个月"]),
        "help": ("帮助", "命令、模式以及\n无法使用时怎么办", None),
        "how": ("工作原理", "一个链接——包含所有服务器", ["波兰", "芬兰", "荷兰", "美国"]),
        "ref": ("邀请好友", "分享访问——\n好友将获得试驾", None),
    }),
    "fa": ("اینترنت با دنده‌ی بالا", {
        "issued": ("حرکت!", "تست‌درایو شروع شد —\nحالا یک دستگاه وصل کنید", ["۳ روز", "۲ دستگاه", "۱۰ گیگ"]),
        "connect": ("اتصال دستگاه", "سه قدم تا شروع", ["۱  Happ", "۲  اشتراک", "۳  حالت خودکار"]),
        "status": ("دسترسی من", "مدت، ترافیک و لینک اشتراک", None),
        "tariffs": ("تعرفه‌ها", "همه‌ی سرورها، حالت خودکار\nو تا ۵ دستگاه در هر تعرفه", ["۱ ماه", "۳ ماه", "۶ ماه", "۱۲ ماه"]),
        "help": ("راهنما", "دستورها، حالت‌ها و\nاگر چیزی کار نکرد", None),
        "how": ("چطور کار می‌کند", "یک لینک — همه‌ی سرورها با هم", ["لهستان", "فنلاند", "هلند", "آمریکا"]),
        "ref": ("دعوت از دوست", "دسترسی را به اشتراک بگذارید —\nدوستتان تست‌درایو می‌گیرد", None),
    }),
}


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
    for lang, (tagline, screens) in BANNER_TEXTS.items():
        out_dir = OUT if lang == "ru" else os.path.join(OUT, lang)
        os.makedirs(out_dir, exist_ok=True)
        hero(tagline=tagline, lang=lang).save(os.path.join(out_dir, "home.jpg"), quality=90, optimize=True,
                                              progressive=True)
        for name, (title, subtitle, chips) in screens.items():
            screen(out_dir, lang, name, title, subtitle, chips)
    # Для профиля бота в BotFather: аватар (/setuserpic) и картинка описания (/setdescriptionpic, 640×360).
    avatar().save(os.path.join(OUT, "avatar.png"))
    hero(size=(640, 360)).save(os.path.join(OUT, "description.jpg"), quality=92)
    print("готово:", OUT)


if __name__ == "__main__":
    sys.exit(main())
