"""Баннеры бота «Avangard VPN» по фирменному листу «Замок» (14.10.2026, вариант 03 · зелёный).

Глубокий зелёный #0B231B, античное золото #B08A3E; знак — башня с тремя зубцами и
замочной скважиной (рисуется векторно по пропорциям листа), надписи — Comfortaa Bold
прописными с разрядкой (scripts/fonts, OFL). Баннеры на всех языках интерфейса:
ru — в корне assets/avangard, остальные — в подпапках; китайский — Hiragino Sans GB,
фарси — системный шрифт через CoreText (render_text.swift: PIL без raqm арабицу не соединяет).

Запуск: python3 scripts/make_avangard_banners.py  → marat_bot/themes/assets/avangard/
"""
from __future__ import annotations

import math
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

GREEN = (11, 35, 27)          # #0B231B
GREEN_LIGHT = (20, 56, 43)
GOLD = (176, 138, 62)         # #B08A3E
GOLD_LIGHT = (214, 184, 120)
IVORY = (242, 235, 221)
MUTED = (160, 176, 166)
W, H = 1280, 720
SS = 3

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "marat_bot", "themes", "assets", "avangard")
COMFORTAA = os.path.join(HERE, "fonts", "Comfortaa-wght.ttf")
HIRAGINO = "/System/Library/Fonts/Hiragino Sans GB.ttc"
# Подписи: строчная кириллица Comfortaa читается плохо («д» как «g»), поэтому мелкий текст —
# скруглённый системный SF Rounded, а Comfortaa остаётся для прописных заголовков, как в листе.
ROUNDED = "/System/Library/Fonts/SFNSRounded.ttf"
SWIFT_SRC = os.path.join(HERE, "render_text.swift")


def comfortaa(size: int, weight: int = 700) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(COMFORTAA, size)
    f.set_variation_by_axes([weight])
    return f


def rounded(size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(ROUNDED, size)
    f.set_variation_by_axes([400, weight])
    return f


# ---------- знак «Замок» ----------

def _slot_outline(r: float = 4.0, steps: int = 8) -> list[tuple[float, float]]:
    """Контур щели скважины: расширяется книзу (23 → 33), нижние углы скруглены радиусом r."""
    top, bottom, tl, tr, bl, br = 86.0, 146.0, 53.0, 76.0, 48.0, 81.0
    pts = [(tl, top), (tr, top)]
    for i in range(steps + 1):  # правый нижний угол
        a = math.pi / 2 * i / steps
        pts.append((br - r + r * math.cos(a), bottom - r + r * math.sin(a)))
    for i in range(steps + 1):  # левый нижний угол
        a = math.pi / 2 + math.pi / 2 * i / steps
        pts.append((bl + r + r * math.cos(a), bottom - r + r * math.sin(a)))
    return pts


def tower_mask(height: int) -> Image.Image:
    """Башня: корпус со скруглённым низом, три зубца сверху, замочная скважина (вырез).
    Пропорции сняты с фирменного листа: ширина 129 к высоте 176."""
    u = height / 176.0
    w = int(round(129 * u)) + 2
    big = Image.new("L", (w * SS, (height + 2) * SS), 0)
    d = ImageDraw.Draw(big)
    s = u * SS
    r_top, r_body = 13 * s, 14 * s
    for x0, x1 in ((0, 26), (51.5, 77.5), (103, 129)):  # зубцы
        d.rounded_rectangle([x0 * s, 0, x1 * s, 40 * s], radius=r_top, fill=255)
    d.rounded_rectangle([0, 26 * s, 129 * s, 176 * s], radius=r_body, fill=255)  # корпус
    d.rectangle([0, 26 * s, 129 * s, 60 * s], fill=255)  # верх корпуса прямой
    cx, cy, r = 64.5 * s, 79 * s, 17 * s  # скважина
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
    d.polygon([(x * s, y * s) for x, y in _slot_outline()], fill=0)
    return big.resize((w, height + 2), Image.LANCZOS)


def paste_tower(im: Image.Image, x: int, y: int, height: int, color: tuple[int, int, int], alpha: float = 1.0) -> int:
    mask = tower_mask(height)
    if alpha < 1:
        mask = mask.point(lambda v: int(v * alpha))
    im.paste(Image.new("RGB", mask.size, color), (x, y), mask)
    return mask.width


# ---------- текст ----------

def _swift_renderer() -> str:
    binary = os.path.join(tempfile.gettempdir(), "avangard_render_text")
    if not os.path.exists(binary) or os.path.getmtime(binary) < os.path.getmtime(SWIFT_SRC):
        subprocess.run(["swiftc", "-O", SWIFT_SRC, "-o", binary], check=True)
    return binary


def text_layer(text: str, size: int, lang: str, weight: int = 700, color: tuple[int, int, int] = IVORY,
               tracking: float = 0.0, body: bool = False) -> Image.Image:
    """Строка на прозрачном слое. tracking — разрядка в долях кегля (для латиницы/кириллицы),
    body — набрать SF Rounded вместо Comfortaa (подписи строчными)."""
    if lang == "fa":
        names = {400: "regular", 500: "medium", 700: "bold", 800: "heavy"}
        out = os.path.join(tempfile.gettempdir(), f"avg_castle_fa_{abs(hash((text, size, weight, color)))}.png")
        subprocess.run([_swift_renderer(), text, str(size), names.get(weight, "bold"), "#%02X%02X%02X" % color, out],
                       check=True)
        return Image.open(out).convert("RGBA")
    if lang == "zh":
        f = ImageFont.truetype(HIRAGINO, size, index=1 if weight >= 600 else 0)
        tracking = 0.0
    elif body:
        f = rounded(size, weight)
    else:
        f = comfortaa(size, weight)
    gap = size * tracking
    widths = [f.getlength(ch) for ch in text]
    total = int(sum(widths) + gap * max(0, len(text) - 1)) + 12
    ascent, descent = f.getmetrics()
    layer = Image.new("RGBA", (max(total, 1), ascent + descent + 12), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = 6.0
    for ch, cw in zip(text, widths):
        d.text((x, 6 + ascent), ch, font=f, fill=color + (255,), anchor="ls")
        x += cw + gap
    return layer


def wordmark(im: Image.Image, cx: float, y: int, size: int, color: tuple[int, int, int] = GOLD) -> None:
    """«AVANGARD» с разрядкой и под ним «— VPN —», как в листе."""
    word = text_layer("AVANGARD", size, "en", weight=600, color=color, tracking=0.16)
    im.alpha_composite(word, (int(cx - word.width / 2), y))
    vpn = text_layer("VPN", int(size * 0.42), "en", weight=600, color=color, tracking=0.6)
    vy = y + word.height + int(size * 0.12)
    im.alpha_composite(vpn, (int(cx - vpn.width / 2), vy))
    d = ImageDraw.Draw(im)
    line_y = vy + vpn.height // 2 + 1
    half = vpn.width / 2 + size * 0.35
    length = size * 0.95
    d.line([(cx - half - length, line_y), (cx - half, line_y)], fill=color, width=max(2, size // 28))
    d.line([(cx + half, line_y), (cx + half + length, line_y)], fill=color, width=max(2, size // 28))


# ---------- фон ----------

def background(size: tuple[int, int] = (W, H), frame: bool = True) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size, GREEN)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse([w * 0.45, -h * 0.5, w * 1.35, h * 1.2], fill=110)
    im.paste(Image.new("RGB", size, GREEN_LIGHT), (0, 0), glow.filter(ImageFilter.GaussianBlur(int(w * 0.12))))
    rgba = im.convert("RGBA")
    if frame:
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        inset = int(min(w, h) * 0.045)
        ImageDraw.Draw(overlay).rounded_rectangle([inset, inset, w - inset, h - inset], radius=int(inset * 1.4),
                                                  outline=GOLD + (70,), width=2)
        rgba.alpha_composite(overlay)
    return rgba


def signature(im: Image.Image, rtl: bool = False) -> None:
    word = text_layer("AVANGARD VPN", 22, "en", weight=600, color=GOLD, tracking=0.22)
    tower_w = tower_mask(40).width
    x = W - 78 - tower_w - 14 - word.width if rtl else 78
    paste_tower(im, x, H - 104, 40, GOLD)
    im.alpha_composite(word, (x + tower_w + 14, H - 98))


def watermark(im: Image.Image, rtl: bool = False) -> None:
    """Крупная полупрозрачная башня сбоку; низ уходит за рамку и обрезается по ней."""
    w, h = im.size
    inset = int(min(w, h) * 0.045)
    inner = Image.new("L", im.size, 0)
    ImageDraw.Draw(inner).rounded_rectangle([inset + 2, inset + 2, w - inset - 2, h - inset - 2],
                                            radius=int(inset * 1.4), fill=255)
    tower = tower_mask(560)
    layer = Image.new("L", im.size, 0)
    layer.paste(tower, (120 if rtl else w - tower.width - 120, 150))
    mask = Image.composite(layer, Image.new("L", im.size, 0), inner).point(lambda v: int(v * 0.09))
    im.paste(Image.new("RGBA", im.size, GOLD + (255,)), (0, 0), mask)


def screen(out_dir: str, lang: str, name: str, title: str, subtitle: str, chips: list[str] | None = None) -> None:
    """Экран: заголовок прописными, подпись, чипы-«печати». Фарси — зеркально, от правого края."""
    rtl = lang == "fa"
    im = background()
    watermark(im, rtl)
    d = ImageDraw.Draw(im)

    def place(layer: Image.Image, x: int, y: int) -> None:
        im.alpha_composite(layer, (W - x - layer.width if rtl else x, y))

    d.line([(W - 150, 168), (W - 84, 168)] if rtl else [(84, 168), (150, 168)], fill=GOLD, width=3)
    y = 196
    size = 64 if lang not in ("zh", "fa") else 70
    for line in title.split("\n"):
        layer = text_layer(line if lang in ("zh", "fa") else line.upper(), size, lang, weight=700, color=GOLD,
                           tracking=0.08)
        place(layer, 78, y)
        y += int(layer.height * 1.02)
    y += 14
    for line in subtitle.split("\n"):
        layer = text_layer(line, 30, lang, weight=500, color=MUTED, body=True)
        place(layer, 80, y)
        y += 44
    if chips:
        x, top = 82, y + 18
        for chip in chips:
            upper = lang not in ("zh", "fa")
            layer = text_layer(chip.upper() if upper else chip, 19 if upper else 22, lang, weight=700, color=IVORY,
                               tracking=0.12 if upper else 0.0)
            w, h = layer.width + 32, 48
            left = W - x - w if rtl else x
            d.rounded_rectangle([left, top, left + w, top + h], radius=h // 2, outline=GOLD, width=2)
            im.alpha_composite(layer, (left + 16, top + (h - layer.height) // 2))
            x += w + 14
    signature(im, rtl)
    im.convert("RGB").save(os.path.join(out_dir, f"{name}.jpg"), quality=92, optimize=True, progressive=True)


def hero(size: tuple[int, int] = (W, H), tagline: str = "", lang: str = "ru") -> Image.Image:
    w, h = size
    im = background(size)
    th = int(h * 0.27)
    tower_w = tower_mask(th).width
    paste_tower(im, int(w / 2 - tower_w / 2), int(h * 0.16), th, GOLD)
    wordmark(im, w / 2, int(h * 0.50), int(h * 0.105))
    if tagline:
        native = lang in ("zh", "fa")  # иероглифы и арабицу не разряжаем и делаем крупнее
        layer = text_layer(tagline if native else tagline.upper(), int(h * (0.038 if native else 0.03)), lang,
                           weight=600, color=MUTED, tracking=0.0 if native else 0.14)
        im.alpha_composite(layer, (int(w / 2 - layer.width / 2), int(h * 0.83)))
    return im.convert("RGB")


def avatar(size: int = 640) -> Image.Image:
    """Аватар из листа: золотое поле (Telegram сам обрежет в круг), тёмно-зелёная башня."""
    im = Image.new("RGB", (size, size), GOLD)
    th = int(size * 0.44)
    tw = tower_mask(th).width
    paste_tower(im, (size - tw) // 2, (size - th) // 2, th, GREEN)
    return im


# Надписи баннеров на языках интерфейса: слоган главной и (заголовок, подпись, чипы) экранов.
BANNER_TEXTS = {
    "ru": ("Ваша крепость в интернете", {
        "issued": ("Ворота\nоткрыты", "Доступ готов —\nосталось подключить устройство", ["3 дня", "2 устройства", "10 ГБ"]),
        "connect": ("Подключение", "Три шага до защиты", ["1  Happ", "2  Подписка", "3  Авто-выбор"]),
        "status": ("Мой доступ", "Срок, трафик и ссылка подписки", None),
        "tariffs": ("Тарифы", "Все серверы, Авто-выбор\nи до 5 устройств в каждом", ["1 мес", "3 мес", "6 мес", "12 мес"]),
        "help": ("Помощь", "Команды, режимы и что делать,\nесли что-то не работает", None),
        "how": ("Как это\nработает", "Одна ссылка — все серверы сразу", ["Германия", "Нидерланды"]),
        "ref": ("Пригласить\nдруга", "Поделитесь доступом —\nдругу достанется пробный период", None),
    }),
    "en": ("Your fortress on the internet", {
        "issued": ("Gates\nopen", "Access is ready —\nnow connect a device", ["3 days", "2 devices", "10 GB"]),
        "connect": ("Connect", "Three steps to protection", ["1  Happ", "2  Subscription", "3  Auto mode"]),
        "status": ("My access", "Term, traffic and subscription link", None),
        "tariffs": ("Plans", "All servers, Auto mode\nand up to 5 devices in each", ["1 mo", "3 mo", "6 mo", "12 mo"]),
        "help": ("Help", "Commands, modes and what to do\nif something stops working", None),
        "how": ("How it\nworks", "One link — every server at once", ["Germany", "Netherlands"]),
        "ref": ("Invite a\nfriend", "Share access —\nyour friend gets a free trial", None),
    }),
    "uk": ("Ваша фортеця в інтернеті", {
        "issued": ("Ворота\nвідчинено", "Доступ готовий —\nзалишилося підключити пристрій", ["3 дні", "2 пристрої", "10 ГБ"]),
        "connect": ("Підключення", "Три кроки до захисту", ["1  Happ", "2  Підписка", "3  Авто-вибір"]),
        "status": ("Мій доступ", "Термін, трафік і посилання підписки", None),
        "tariffs": ("Тарифи", "Усі сервери, Авто-вибір\nі до 5 пристроїв у кожному", ["1 міс", "3 міс", "6 міс", "12 міс"]),
        "help": ("Допомога", "Команди, режими і що робити,\nякщо щось не працює", None),
        "how": ("Як це\nпрацює", "Одне посилання — усі сервери одразу", ["Німеччина", "Нідерланди"]),
        "ref": ("Запросити\nдруга", "Поділіться доступом —\nдруг отримає пробний період", None),
    }),
    "zh": ("你在互联网上的堡垒", {
        "issued": ("大门已开", "访问已就绪——\n现在连接设备", ["3 天", "2 台设备", "10 GB"]),
        "connect": ("连接设备", "三步即可受到保护", ["1  Happ", "2  订阅", "3  自动选择"]),
        "status": ("我的访问", "期限、流量和订阅链接", None),
        "tariffs": ("套餐", "所有服务器、自动选择\n每个套餐最多 5 台设备", ["1 个月", "3 个月", "6 个月", "12 个月"]),
        "help": ("帮助", "命令、模式以及\n无法使用时怎么办", None),
        "how": ("工作原理", "一个链接——包含所有服务器", ["德国", "荷兰"]),
        "ref": ("邀请好友", "分享访问——\n好友将获得免费试用", None),
    }),
    "fa": ("دژ شما در اینترنت", {
        "issued": ("دروازه باز شد", "دسترسی آماده است —\nحالا یک دستگاه وصل کنید", ["۳ روز", "۲ دستگاه", "۱۰ گیگ"]),
        "connect": ("اتصال دستگاه", "سه قدم تا امنیت", ["۱  Happ", "۲  اشتراک", "۳  انتخاب خودکار"]),
        "status": ("دسترسی من", "مدت، ترافیک و لینک اشتراک", None),
        "tariffs": ("تعرفه‌ها", "همه‌ی سرورها، انتخاب خودکار\nو تا ۵ دستگاه در هر تعرفه", ["۱ ماه", "۳ ماه", "۶ ماه", "۱۲ ماه"]),
        "help": ("راهنما", "دستورها، حالت‌ها و\nاگر چیزی کار نکرد", None),
        "how": ("چطور کار می‌کند", "یک لینک — همه‌ی سرورها با هم", ["آلمان", "هلند"]),
        "ref": ("دعوت از دوست", "دسترسی را به اشتراک بگذارید —\nدوستتان دوره‌ی آزمایشی می‌گیرد", None),
    }),
}


def main() -> None:
    for lang, (tagline, screens) in BANNER_TEXTS.items():
        out_dir = OUT if lang == "ru" else os.path.join(OUT, lang)
        os.makedirs(out_dir, exist_ok=True)
        hero(tagline=tagline, lang=lang).save(os.path.join(out_dir, "home.jpg"), quality=92, optimize=True,
                                              progressive=True)
        for name, (title, subtitle, chips) in screens.items():
            screen(out_dir, lang, name, title, subtitle, chips)
    # Для профиля бота в BotFather: аватар (/setuserpic) и картинка описания (/setdescriptionpic, 640×360).
    avatar().save(os.path.join(OUT, "avatar.png"))
    hero(size=(640, 360)).save(os.path.join(OUT, "description.jpg"), quality=92)
    print("готово:", OUT)


if __name__ == "__main__":
    main()
