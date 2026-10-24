"""
fa_text.py - ابزارهای مشترک متن فارسی برای همهٔ اسکریپت‌های این بسته.

این فایل در چند پوشه کپی شده تا هر اسکیل به‌تنهایی هم کار کند.
نسخهٔ اصلی در tools/fa_text.py است؛ بعد از هر تغییر: python tools/sync_fa_text.py

نکته‌های فارسی که اینجا رعایت می‌شود:
  - نیم‌فاصله (U+200C) جزء کلمه است، نه «کاراکتر نامرئی». «می‌خوام» یک کلمه است.
  - ي و ك عربی به ی و ک فارسی تبدیل می‌شوند.
  - رقم‌های فارسی (۰-۹)، عربی (٠-٩) و لاتین هر سه «عدد» حساب می‌شوند.
  - جمله‌ها با . ! ? ؟ … و خط جدید جدا می‌شوند.
"""

import re
import sys

ZWNJ = "‌"

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"

_TO_EN = str.maketrans(FA_DIGITS + AR_DIGITS, EN_DIGITS * 2)
_TO_FA = str.maketrans(EN_DIGITS + AR_DIGITS, FA_DIGITS * 2)
_ARABIC_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "هٔ", "ة": "ه"})

PERSIAN_LETTER = r"؀-ۿﭐ-﷿ﹰ-﻿"
# a word: letters/digits (any script) joined by ZWNJ, plus $ % ' -
WORD_RE = re.compile(r"[\w" + ZWNJ + r"$%'’\-]+", re.UNICODE)
SENT_RE = re.compile(r"[^.!?؟…\n]+[.!?؟…]*")
NUMBER_RE = re.compile(r"[$]?\s?[\d۰-۹٠-٩][\d۰-۹٠-٩,٬.]*\s?(?:%|٪)?")
LATIN_NAME_RE = re.compile(r"\b[A-Z][A-Za-z0-9]{1,}\b")
HASHTAG_RE = re.compile(r"(?:^|\s)#[\w" + ZWNJ + r"_]+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")
PERSIAN_RE = re.compile(r"[" + PERSIAN_LETTER + r"]")


def setup_stdout():
    """ویندوز معمولاً خروجی را با cp1252 می‌نویسد و فارسی را خراب می‌کند."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def to_en_digits(text):
    return text.translate(_TO_EN)


def to_fa_digits(text):
    return text.translate(_TO_FA)


def normalize(text):
    """یکدست کردن حروف عربی؛ نیم‌فاصله‌ها دست نمی‌خورند."""
    return text.translate(_ARABIC_LETTERS)


def is_persian(text):
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return False
    fa = len(PERSIAN_RE.findall(text))
    return fa / len(letters) >= 0.4


def words(text):
    """کلمه‌ها، با نیم‌فاصله به‌عنوان بخشی از کلمه. «۱۸٬۰۰۰» یک کلمه است."""
    t = re.sub(r"(?<=[\d۰-۹٠-٩])[,٬](?=[\d۰-۹٠-٩])", "", normalize(text))
    return [w.strip("-'’") for w in WORD_RE.findall(t) if w.strip("-'’")]


def low(token):
    return normalize(token).lower().strip("'’")


def sentences(text):
    return [s.strip() for s in SENT_RE.findall(normalize(text)) if s.strip()]


def numbers(text):
    return [n.strip() for n in NUMBER_RE.findall(text) if re.search(r"[\d۰-۹٠-٩]", n)]


def latin_names(text):
    """در فارسی حرف بزرگ نداریم؛ فقط اسم‌های لاتین (ChatGPT، Canva) را می‌شود تشخیص داد."""
    return LATIN_NAME_RE.findall(text)


def visible_len(text):
    """طول متن بدون نیم‌فاصله، همان‌طور که چشم می‌بیند."""
    return len(text.replace(ZWNJ, ""))


def bar(score, width=24):
    filled = round(max(0, min(100, score)) / 100 * width)
    return "#" * filled + "." * (width - filled)


def clamp(n):
    return max(0.0, min(100.0, n))


# ---------------------------------------------------------------------------
# زیرنویس زمان‌دار (SRT، VTT، JSON خروجی Whisper) — مشترک بین yt-edit، yt-chapters، yt-shorts و yt-retention

def parse_ts(s):
    """«00:01:02,500» یا «1:02.5» یا «۰۱:۰۲» → ثانیه."""
    s = to_en_digits(s.strip()).replace(",", ".")
    p = s.split(":")
    if len(p) == 3:
        return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
    if len(p) == 2:
        return int(p[0]) * 60 + float(p[1])
    return float(p[0])


def load_transcript(path):
    """فهرست (شروع، پایان، متن) از SRT، VTT یا JSON (Whisper)."""
    import json as _json
    raw = open(path, encoding="utf-8-sig", errors="replace").read()
    if path.lower().endswith(".json"):
        d = _json.loads(raw)
        segs = d.get("segments", []) if isinstance(d, dict) else d
        return [(float(s["start"]), float(s["end"]), normalize((s.get("text") or "").strip()))
                for s in segs]
    cues, cur = [], None
    for line in raw.splitlines():
        ln = to_en_digits(line)
        m = re.match(r"\s*(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)", ln)
        if m:
            cur = [parse_ts(m.group(1)), parse_ts(m.group(2)), []]
            cues.append(cur)
        elif cur is not None and line.strip() and not ln.strip().isdigit() \
                and not line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
            cur[2].append(re.sub(r"<[^>]+>", "", line.strip()))
    return [(a, b, normalize(" ".join(t))) for a, b, t in cues if t]


def mmss(t):
    """زمان چپتر یوتیوب: «0:00»، «12:05» یا «1:02:03» — همیشه با رقم لاتین."""
    t = int(t)
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


FA_STOP = set("""
و در به از که را رو با برای این اون آن یه یک تا هم چه چی چرا چطور من تو شما ما او اونا ایشون است هست
بود بودم هستم نیست می نمی کن کرد کردم کنم کنی کنید کنه کنن شد شده شدم میشه می‌شه بشه باشه دیگه هر همه
بدون اگه اگر ولی اما پس حالا خب خوب یعنی مثلاً مثلا اینجا اونجا اینو اونو اینه اونه داره دارم داری دارید
یکی چیزی کار خیلی واقعاً واقعا فقط الان بعد قبل وقتی چون باید نباید میخوام می‌خوام بگم گفتم ببینیم ببین
اینکه اونکه ها های ای ی ام ات اش مون تون شون نه آره بله رفت میره میاد اومد میگه می‌گه گفت کنیم کردیم
""".split())


def keywords(text, minlen=3):
    """کلمه‌های محتوایی (بدون کلمه‌های پرتکرار) برای تشخیص تغییر موضوع."""
    out = set()
    for w in words(text):
        k = low(w).replace(ZWNJ, "")
        if len(k) >= minlen and k not in FA_STOP and not re.fullmatch(r"[\d۰-۹٠-٩.,]+", k):
            out.add(k)
    return out
