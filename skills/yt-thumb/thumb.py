#!/usr/bin/env python3
"""
thumb.py - ساخت تامبنیل فارسی یوتیوب و آپارات (۱۲۸۰×۷۲۰، ۱۶:۹) از یک spec ساده.

موتور همان روش instagram-fa است (Pillow + libraqm برای چسباندن درست حروف فارسی و راست‌به‌چپ، با
فونت‌های وزیرمتن و لاله‌زار)، ولی چیدمان‌ها برای تامبنیل افقی طراحی شده‌اند:

  bold     پس‌زمینهٔ رنگ برند، ۲ تا ۴ کلمهٔ درشت، یک کلمه با رنگ تأکید
  split    عکس (معمولاً چهره) یک طرف، متن درشت طرف دیگر
  photo    عکس تمام‌صفحه با سایهٔ رنگی و متن روی آن
  versus   دو گزینه رودررو با نشان «یا» در وسط
  number   یک عدد خیلی بزرگ و یک برچسب کوتاه

قواعدی که خودکار رعایت می‌شود:
  - گوشهٔ پایین‌راست خالی می‌ماند (یوتیوب مدت ویدیو را آنجا می‌گذارد).
  - متن تا جایی که جا شود درشت می‌شود؛ اگر در کمترین اندازهٔ خوانا هم جا نشد، هشدار می‌دهد.
  - رقم‌ها طبق brand.json فارسی یا لاتین می‌شوند.
  - کلمه‌ای که بین دو ستاره است (*برنده*) با رنگ تأکید برجسته می‌شود.

spec (JSON):
  {"layout": "split", "text": "ارزون‌ترین *برنده شد*", "kicker": "تست ۵ میکروفون",
   "photo": "face.jpg", "photo_side": "left", "focus": [0.5, 0.35]}
  versus:  {"layout": "versus", "a": "ChatGPT", "b": "Claude", "kicker": "یک هفته کار واقعی"}
  number:  {"layout": "number", "number": "۴۰٪", "text": "از بیننده‌ها همین‌جا رفتن"}

استفاده:
  python thumb.py spec.json --out thumb.png [--channel <پوشهٔ کانال>] [--preview]
  python thumb.py spec1.json spec2.json spec3.json --out-dir thumbs/ --preview   # چند نسخه برای مقایسه
  python thumb.py --check

--preview یک برگهٔ مقایسه می‌سازد: هر نسخه در اندازهٔ واقعی فید موبایل، نتیجهٔ جست‌وجو و ستون کناری،
چون تامبنیل در اندازهٔ کوچک دیده می‌شود، نه در ۱۲۸۰ پیکسل.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
W, H = 1280, 720
SAFE_BR = (1280 - 210, 720 - 90)       # گوشهٔ پایین‌راست برای نشان مدت ویدیو
FA_DIG = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
PERSIAN = re.compile(r"[؀-ۿﭐ-﷿ﹰ-﻿]")
LTR_TOKEN = re.compile(r"^[A-Za-z0-9$%+#@&._\-/:]+$")
DEFAULT_BRAND = {"primary": "#1F6F5C", "accent": "#F2B134", "digits": "fa", "display_font": ""}

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, features
except ImportError:
    print("Pillow نصب نیست: pip install pillow", file=sys.stderr)
    sys.exit(2)


def setup_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def has_raqm():
    try:
        return bool(features.check("raqm"))
    except Exception:
        return False


RAQM = has_raqm()
try:
    import arabic_reshaper  # noqa: E402
    from bidi.algorithm import get_display  # noqa: E402
    RESHAPER = True
except Exception:
    RESHAPER = False


def check():
    ok = RAQM or RESHAPER
    print(json.dumps({"pillow": True, "raqm": RAQM, "reshaper_fallback": RESHAPER, "ready": ok,
                      "fix": None if ok else "pip install arabic-reshaper python-bidi"}, ensure_ascii=False))
    return ok


# ---------------------------------------------------------------- colours

def rgb(h, a=255):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def on(c):
    """سفید یا تیره، هر کدام کنتراست بیشتری دارد."""
    L = lum(c)
    white = 1.05 / (L + 0.05)
    dark = (L + 0.05) / (lum((20, 22, 30)) + 0.05)
    return (255, 255, 255, 255) if white >= dark else (20, 22, 30, 255)


def darker(c, t=0.35):
    return tuple(int(v * (1 - t)) for v in c[:3]) + (255,)


# ---------------------------------------------------------------- fonts

_FONT_CACHE = {}


def font_path(name, user_dirs):
    name = (name or "").strip().lower()
    builtin = {"vazir": "Vazirmatn-Black.ttf", "vazirmatn": "Vazirmatn-Black.ttf", "": "Vazirmatn-Black.ttf",
               "vazir-bold": "Vazirmatn-Bold.ttf", "vazir-medium": "Vazirmatn-Medium.ttf",
               "lalezar": "lalezar-arabic-400-normal.woff2"}
    if name in builtin:
        return os.path.join(FONT_DIR, builtin[name])
    for d in user_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().startswith(name) and f.lower().endswith((".ttf", ".otf", ".woff2", ".woff")):
                    return os.path.join(d, f)
    return os.path.join(FONT_DIR, "Vazirmatn-Black.ttf")


def font(path, size):
    key = (path, int(size))
    if key not in _FONT_CACHE:
        kw = {"layout_engine": ImageFont.Layout.RAQM} if RAQM else {}
        _FONT_CACHE[key] = ImageFont.truetype(path, int(size), **kw)
    return _FONT_CACHE[key]


# ---------------------------------------------------------------- text shaping

def fa_digits(text, on_=True):
    if not on_:
        return text
    text = re.sub(r"(?<=\d)\s?%", "٪", text)
    return re.sub(r"(?<![A-Za-z\-_.])\d+(?:[.,٫]\d+)*(?![A-Za-z])", lambda m: m.group().translate(FA_DIG), text)


def shape(word):
    """متن یک کلمه برای رسم. با raqm خود Pillow می‌چسباند؛ بدون آن، reshaper."""
    if RAQM or not PERSIAN.search(word):
        return word
    return get_display(arabic_reshaper.reshape(word)) if RESHAPER else word


def text_len(f, s):
    if RAQM:
        return f.getlength(s, direction="rtl" if PERSIAN.search(s) else "ltr")
    return f.getlength(shape(s))


def parse_runs(text):
    """«ارزون‌ترین *برنده شد*» → فهرست کلمه‌ها با پرچم برجسته."""
    out, hl = [], False
    for part in re.split(r"(\*)", text):
        if part == "*":
            hl = not hl
            continue
        for w in part.split():
            out.append((w, hl))
    return out


def group_ltr(words):
    """کلمه‌های لاتین پشت سر هم یک تکهٔ چپ‌به‌راست می‌شوند تا ترتیبشان برعکس نشود."""
    groups = []
    for w, hl in words:
        is_ltr = bool(LTR_TOKEN.match(w)) and not PERSIAN.search(w)
        if groups and is_ltr and groups[-1][2] and groups[-1][1] == hl:
            groups[-1] = (groups[-1][0] + " " + w, hl, True)
        else:
            groups.append((w, hl, is_ltr))
    return groups


def wrap(groups, f, max_w, max_lines):
    """تقسیم متوازن کلمه‌ها در حداکثر max_lines خط."""
    sp = text_len(f, " ")
    best = None
    n = len(groups)
    for lines_n in range(1, min(max_lines, n) + 1):
        # تقسیم حریصانه با عرض هدف = کل / تعداد خط
        total = sum(text_len(f, g[0]) for g in groups) + sp * (n - 1)
        target = total / lines_n
        lines, cur, cur_w = [], [], 0
        for g in groups:
            gw = text_len(f, g[0])
            add = gw + (sp if cur else 0)
            if cur and (cur_w + add > max_w or (cur_w + add > target * 1.15 and len(lines) < lines_n - 1)):
                lines.append(cur)
                cur, cur_w = [g], gw
            else:
                cur.append(g)
                cur_w += add
        if cur:
            lines.append(cur)
        widths = [sum(text_len(f, g[0]) for g in ln) + sp * (len(ln) - 1) for ln in lines]
        if len(lines) <= max_lines and max(widths) <= max_w:
            best = (lines, widths)
            break
    return best


def fit(text, fpath, box_w, box_h, max_lines=3, max_size=210, min_size=56, line_gap=1.12):
    groups = group_ltr(parse_runs(text))
    if not groups:
        return None
    size = max_size
    while size >= min_size:
        f = font(fpath, size)
        res = wrap(groups, f, box_w, max_lines)
        if res:
            lines, widths = res
            lh = size * line_gap
            if lh * len(lines) <= box_h:
                return {"font": f, "size": size, "lines": lines, "widths": widths, "lh": lh, "overflow": False}
        size -= 6
    f = font(fpath, min_size)
    res = wrap(groups, f, box_w * 1.5, max_lines + 2) or ([[g for g in groups]], [box_w])
    return {"font": f, "size": min_size, "lines": res[0], "widths": res[1], "lh": min_size * line_gap,
            "overflow": True}


def draw_block(img, block, x_right, y_top, color, hl_bg, hl_fg, align="right", box_w=None,
               stroke=0, stroke_color=(0, 0, 0, 255)):
    d = ImageDraw.Draw(img)
    f, lh = block["font"], block["lh"]
    sp = text_len(f, " ")
    pad = block["size"] * 0.12
    for i, (ln, lw) in enumerate(zip(block["lines"], block["widths"])):
        y = y_top + i * lh
        if align == "center" and box_w:
            x = x_right - (box_w - lw) / 2
        else:
            x = x_right
        if hl_bg:                            # کادر تأکید: کلمه‌های برجستهٔ پشت سر هم یک کادر
            xx, run = x, None
            for word, hl, _ in ln:
                ww = text_len(f, word)
                if hl:
                    run = [xx - ww, run[1] if run else xx]
                elif run:
                    d.rounded_rectangle([run[0] - pad, y + lh * 0.06, run[1] + pad, y + lh * 0.98],
                                        radius=int(pad * 1.2), fill=hl_bg)
                    run = None
                xx -= ww + sp
            if run:
                d.rounded_rectangle([run[0] - pad, y + lh * 0.06, run[1] + pad, y + lh * 0.98],
                                    radius=int(pad * 1.2), fill=hl_bg)
        for word, hl, is_ltr in ln:          # راست‌به‌چپ: کلمهٔ اول سمت راست
            ww = text_len(f, word)
            x0 = x - ww
            fill = hl_fg if (hl and hl_bg) else (hl_fg if hl else color)
            kw = {}
            if RAQM:
                kw["direction"] = "ltr" if is_ltr else "rtl"
            d.text((x0, y + lh * 0.5), shape(word), font=f, fill=fill, anchor="lm",
                   stroke_width=stroke if not (hl and hl_bg) else 0, stroke_fill=stroke_color, **kw)
            x = x0 - sp


def place_photo(img, path, box, focus=(0.5, 0.4)):
    ph = Image.open(path)
    ph = ImageOps.exif_transpose(ph).convert("RGBA")
    x0, y0, x1, y1 = box
    fitted = ImageOps.fit(ph, (x1 - x0, y1 - y0), method=Image.LANCZOS, centering=tuple(focus))
    img.alpha_composite(fitted, (x0, y0))


def gradient(w, h, c, side="right", strength=0.92):
    g = Image.new("RGBA", (w, h))
    px = g.load()
    for x in range(w):
        t = x / (w - 1)
        a = (t if side == "right" else 1 - t)
        a = max(0.0, min(1.0, (a - 0.15) / 0.85)) ** 1.2 * strength
        for y in range(h):
            px[x, y] = (c[0], c[1], c[2], int(255 * a))
    return g


# ---------------------------------------------------------------- layouts

def kicker(img, text, x_right, y, bg, fg, fpath):
    if not text:
        return 0
    f = font(fpath, 44)
    w = text_len(f, text)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([x_right - w - 52, y, x_right, y + 76], radius=38, fill=bg)
    kw = {"direction": "rtl"} if RAQM and PERSIAN.search(text) else {}
    d.text((x_right - 26, y + 39), shape(text), font=f, fill=fg, anchor="rm", **kw)
    return 76 + 24


def signature(img, brand, accent):
    sig = (brand.get("thumb") or {}).get("signature", "bar") or "bar"
    d = ImageDraw.Draw(img)
    if sig == "bar":
        d.rectangle([0, 0, W, 16], fill=accent)
    elif sig == "corner":
        d.polygon([(W, 0), (W - 150, 0), (W, 150)], fill=accent)
    elif sig == "frame":
        d.rectangle([8, 8, W - 9, H - 9], outline=accent, width=16)


def render(spec, brand, user_font_dirs, spec_dir="."):
    digits = brand.get("digits", "fa") == "fa"
    primary, accent = rgb(brand.get("primary", "#1F6F5C")), rgb(brand.get("accent", "#F2B134"))
    disp = font_path(spec.get("font") or brand.get("display_font"), user_font_dirs)
    kfont = font_path("vazir-bold", user_font_dirs)
    layout = spec.get("layout", "bold")
    text = fa_digits(spec.get("text", ""), digits)
    kick = fa_digits(spec.get("kicker", ""), digits)
    bg = rgb(spec["bg"]) if spec.get("bg") else primary
    img = Image.new("RGBA", (W, H), bg)
    M = 64
    warn = []

    def photo_path():
        p = spec.get("photo")
        if not p:
            return None
        p = p if os.path.isabs(p) else os.path.join(spec_dir, p)
        if not os.path.exists(p):
            warn.append(f"عکس پیدا نشد: {p}")
            return None
        return p

    if layout == "split":
        side = spec.get("photo_side", "left")
        pw = int(W * spec.get("photo_ratio", 0.44))
        p = photo_path()
        box = (0, 0, pw, H) if side == "left" else (W - pw, 0, W, H)
        if p:
            place_photo(img, p, box, spec.get("focus", (0.5, 0.35)))
        else:
            ImageDraw.Draw(img).rectangle(box, fill=darker(bg, 0.25))
        # لبهٔ مورب بین عکس و متن
        d = ImageDraw.Draw(img)
        if side == "left":
            d.polygon([(pw - 60, 0), (W, 0), (W, H), (pw - 120, H)], fill=bg)
            d.polygon([(pw - 60, 0), (pw - 40, 0), (pw - 100, H), (pw - 120, H)], fill=accent)
            tx_right, tx_w = W - M, W - pw - M - 30
        else:
            x = W - pw
            d.polygon([(x + 60, 0), (0, 0), (0, H), (x + 120, H)], fill=bg)
            d.polygon([(x + 60, 0), (x + 40, 0), (x + 100, H), (x + 120, H)], fill=accent)
            tx_right, tx_w = x - 30, x - M - 30
        top = M + 10
        top += kicker(img, kick, tx_right, top, accent, on(accent), kfont)
        blk = fit(text, disp, tx_w, H - top - 110, max_lines=3)
        y = top + max(0, (H - top - 110 - blk["lh"] * len(blk["lines"])) / 2)
        draw_block(img, blk, tx_right, y, on(bg), accent, on(accent))

    elif layout == "photo":
        p = photo_path()
        if p:
            place_photo(img, p, (0, 0, W, H), spec.get("focus", (0.5, 0.4)))
        shade = darker(bg, 0.55)
        img.alpha_composite(gradient(W, H, shade, side="right"))
        tx_w = int(W * 0.58)
        top = M + 10
        top += kicker(img, kick, W - M, top, accent, on(accent), kfont)
        blk = fit(text, disp, tx_w, H - top - 120, max_lines=3)
        y = H - 120 - blk["lh"] * len(blk["lines"])
        draw_block(img, blk, W - M, max(top, y), (255, 255, 255, 255), accent, on(accent),
                   stroke=max(2, blk["size"] // 28), stroke_color=(0, 0, 0, 200))

    elif layout == "versus":
        a, b = fa_digits(spec.get("a", ""), digits), fa_digits(spec.get("b", ""), digits)
        ca = rgb(spec["color_a"]) if spec.get("color_a") else primary
        cb = rgb(spec["color_b"]) if spec.get("color_b") else darker(accent, 0.05)
        d = ImageDraw.Draw(img)
        d.polygon([(W // 2 + 50, 0), (W, 0), (W, H), (W // 2 - 50, H)], fill=ca)   # راست = گزینهٔ اول
        d.polygon([(0, 0), (W // 2 + 50, 0), (W // 2 - 50, H), (0, H)], fill=cb)
        top = 150 if kick else 70
        for label, color, xr, w in ((a, ca, W - M, W // 2 - M - 90), (b, cb, W // 2 - 110, W // 2 - M - 90)):
            blk = fit(label, disp, w, H - top - 130, max_lines=2, max_size=170)
            y = top + (H - top - 130 - blk["lh"] * len(blk["lines"])) / 2
            draw_block(img, blk, xr, y, on(color), None, on(color), align="center", box_w=w)
        r = 86
        d.ellipse([W // 2 - r, H // 2 - r + 20, W // 2 + r, H // 2 + r + 20], fill=(255, 255, 255, 255),
                  outline=(20, 22, 30, 255), width=8)
        vf = font(disp, 84)
        kw = {"direction": "rtl"} if RAQM else {}
        d.text((W // 2, H // 2 + 20), shape(spec.get("vs", "یا")), font=vf, fill=(20, 22, 30, 255), anchor="mm", **kw)
        if kick:
            f = font(kfont, 46)
            kw2 = {"direction": "rtl"} if RAQM and PERSIAN.search(kick) else {}
            wk = text_len(f, kick)
            d.rounded_rectangle([W // 2 - wk / 2 - 30, 40, W // 2 + wk / 2 + 30, 116], radius=38, fill=(20, 22, 30, 230))
            d.text((W // 2, 78), shape(kick), font=f, fill=(255, 255, 255, 255), anchor="mm", **kw2)

    elif layout == "number":
        num = fa_digits(str(spec.get("number", "")), digits)
        p = photo_path()
        right_w = W - M * 2
        if p:
            pw = int(W * 0.40)
            place_photo(img, p, (0, 0, pw, H), spec.get("focus", (0.5, 0.35)))
            ImageDraw.Draw(img).rectangle([pw, 0, pw + 14, H], fill=accent)
            right_w = W - pw - M * 2
        top = M
        top += kicker(img, kick, W - M, top, accent, on(accent), kfont)
        nb = fit(num, disp, right_w, 330, max_lines=1, max_size=330, min_size=120, line_gap=1.0)
        draw_block(img, nb, W - M, top - 10, accent, None, accent)
        y2 = top - 10 + nb["lh"] + 10
        blk = fit(text, disp, right_w, H - y2 - 100, max_lines=2, max_size=110, min_size=48)
        draw_block(img, blk, W - M, y2, on(bg), accent, on(accent))

    else:  # bold
        layout = "bold"
        d = ImageDraw.Draw(img)
        d.rectangle([0, H - 26, W, H], fill=darker(bg, 0.3))
        top = M + 20
        top += kicker(img, kick, W - M, top, accent, on(accent), kfont)
        blk = fit(text, disp, W - M * 2, H - top - 120, max_lines=3)
        y = top + max(0, (H - top - 120 - blk["lh"] * len(blk["lines"])) / 2)
        draw_block(img, blk, W - M, y, on(bg), accent, on(accent))

    signature(img, brand, accent)
    return img.convert("RGB"), warn, (locals().get("blk") or {}).get("overflow", False)


def preview(images, names, out):
    """هر نسخه در اندازه‌های واقعی: فید موبایل (۳۶۰)، جست‌وجوی دسکتاپ (۳۶۰×۲۰۲)، ستون کناری (۱۶۸×۹۴)."""
    sizes = [(640, 360), (360, 202), (168, 94)]
    pad, label_h = 24, 44
    row_h = 360 + label_h + pad
    sheet = Image.new("RGB", (pad + sum(s[0] + pad for s in sizes), pad + row_h * len(images)), (246, 247, 249))
    d = ImageDraw.Draw(sheet)
    lf = font(os.path.join(FONT_DIR, "Vazirmatn-Bold.ttf"), 22)
    for r, (im, nm) in enumerate(zip(images, names)):
        y = pad + r * row_h
        x = pad
        for w, h in sizes:
            sheet.paste(im.resize((w, h), Image.LANCZOS), (x, y + label_h))
            x += w + pad
        kw = {"direction": "rtl"} if RAQM else {}
        d.text((sheet.width - pad, y + label_h / 2), shape(f"{nm}  ·  ۶۴۰ / ۳۶۰ / ۱۶۸ پیکسل"), font=lf,
               fill=(40, 44, 52), anchor="rm", **kw)
    sheet.save(out)


def load_brand(channel_dir, override=None):
    b = dict(DEFAULT_BRAND)
    if channel_dir and os.path.exists(os.path.join(channel_dir, "brand.json")):
        with open(os.path.join(channel_dir, "brand.json"), encoding="utf-8") as f:
            b.update(json.load(f))
    b.update(override or {})
    return b


def active_channel():
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "yt-setup"))
        import channel  # noqa
        return channel.channel_dir(), channel.home()
    except Exception:
        return None, None


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="تامبنیل فارسی یوتیوب و آپارات")
    ap.add_argument("specs", nargs="*")
    ap.add_argument("--out", help="خروجی برای یک spec")
    ap.add_argument("--out-dir", help="پوشهٔ خروجی برای چند spec")
    ap.add_argument("--channel", help="پوشهٔ کانال (برای brand.json)؛ پیش‌فرض کانال فعال")
    ap.add_argument("--preview", action="store_true", help="برگهٔ مقایسه در اندازه‌های واقعی")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        sys.exit(0 if check() else 1)
    if not a.specs:
        ap.print_help()
        sys.exit(1)
    if not (RAQM or RESHAPER):
        print("برای فارسی، Pillow باید libraqm داشته باشد یا این دو نصب شوند: pip install arabic-reshaper python-bidi",
              file=sys.stderr)
        sys.exit(2)
    ch_dir, home = active_channel()
    ch_dir = a.channel or ch_dir
    brand = load_brand(ch_dir)
    font_dirs = [d for d in ((ch_dir and os.path.join(ch_dir, "fonts")), (home and os.path.join(home, "fonts"))) if d]
    outs, imgs, names, code = [], [], [], 0
    for i, sp in enumerate(a.specs):
        with open(sp, encoding="utf-8") as f:
            spec = json.load(f)
        im, warn, over = render(spec, load_brand(ch_dir, spec.get("brand")), font_dirs, os.path.dirname(os.path.abspath(sp)))
        if a.out and len(a.specs) == 1:
            out = a.out
        else:
            od = a.out_dir or "."
            os.makedirs(od, exist_ok=True)
            out = os.path.join(od, os.path.splitext(os.path.basename(sp))[0] + ".png")
        im.save(out, optimize=True)
        outs.append(out)
        imgs.append(im)
        names.append(os.path.splitext(os.path.basename(sp))[0])
        msg = f"ساخته شد: {out}"
        if over:
            msg += "  ⚠ متن در کمترین اندازهٔ خوانا هم جا نشد؛ کوتاهش کن (۲ تا ۴ کلمه)"
            code = 3
        for w in warn:
            msg += f"  ⚠ {w}"
        print(msg)
    if a.preview:
        pv = os.path.join(os.path.dirname(outs[0]) or ".", "preview.png")
        preview(imgs, names, pv)
        print(f"برگهٔ مقایسه: {pv}")
    sys.exit(code)


if __name__ == "__main__":
    main()
