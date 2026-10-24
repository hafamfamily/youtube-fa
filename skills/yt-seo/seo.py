#!/usr/bin/env python3
"""
seo.py - بررسی توضیحات، تگ‌ها و هشتگ‌های یک ویدیوی یوتیوب پیش از انتشار.

ابزار تازهٔ youtube-fa. فقط قاعده‌های مکانیکی را بررسی می‌کند، نه کیفیت نوشته را:
  - دو خط اول توضیحات (پیش از «بیشتر») حرف اصلی و کلمهٔ جست‌وجو را دارد؟
  - کلمه‌های جست‌وجو در عنوان و اول توضیحات آمده‌اند؟
  - چپترها (اگر هست) طبق قواعد یوتیوب درست‌اند؟
  - تگ‌ها: مجموع حداکثر ۵۰۰ حرف (سقف یوتیوب)؛ تگ تکراری.
  - هشتگ‌ها: سه هشتگ اول بالای عنوان نشان داده می‌شود؛ بیش از ۶۰ هشتگ یعنی یوتیوب همه را نادیده می‌گیرد.
  - لینک‌ها: لینک کوتاه‌شده‌ای که مقصدش معلوم نیست.

  python seo.py --title "..." --desc description.txt --tags "تگ۱, تگ۲" --queries "کوئری ۱|کوئری ۲"
  python seo.py --desc description.txt --json
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import setup_stdout, words, low, visible_len, ZWNJ, to_en_digits, parse_ts  # noqa: E402

FOLD = 125          # تقریباً آنچه پیش از «بیشتر» دیده می‌شود (بسته به دستگاه فرق می‌کند)
TAGS_MAX = 500
HASH_MAX = 60
SHORTENERS = re.compile(r"https?://(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|cutt\.ly|is\.gd|rb\.gy)/", re.I)
CH_RE = re.compile(r"^\s*\(?((?:\d{1,2}:)?\d{1,2}:\d{2})\)?\s+\S")


def stems(text):
    return {low(w).replace(ZWNJ, "") for w in words(text) if len(w) > 1}


def query_hit(query, text):
    q = stems(query)
    t = stems(text)
    return len(q & t) / len(q) if q else 0


def check(title, desc, tags, queries):
    issues, good, notes = [], [], []
    lines = [l for l in desc.splitlines() if l.strip()]
    head = " ".join(lines[:2])
    fold = head[:FOLD + head[:FOLD].count(ZWNJ)]
    if not desc.strip():
        issues.append("توضیحات خالی است")
    elif visible_len(lines[0]) < 40:
        issues.append(f"خط اول توضیحات کوتاه است ({visible_len(lines[0])} حرف)؛ یک جملهٔ کامل بنویس که بگوید بیننده چه می‌گیرد")
    else:
        good.append("خط اول توضیحات یک جملهٔ کامل است")
    if re.search(r"https?://", fold) and not re.search(r"[؀-ۿ]{3}", fold):
        issues.append("بالای «بیشتر» فقط لینک است؛ اول یک جمله دربارهٔ ویدیو بنویس")

    for q in queries:
        in_title = query_hit(q, title) if title else 0
        in_fold = query_hit(q, fold)
        if in_title >= 0.6 or in_fold >= 0.6:
            good.append(f"«{q}» در {'عنوان' if in_title >= 0.6 else 'اول توضیحات'} آمده")
        else:
            issues.append(f"کوئری «{q}» نه در عنوان است نه در دو خط اول توضیحات")

    ch = []
    for l in desc.splitlines():
        m = CH_RE.match(to_en_digits(l))
        if m:
            ch.append(int(parse_ts(m.group(1))))
    if ch:
        if len(ch) < 3 or ch[0] != 0 or any(b - a < 10 for a, b in zip(ch, ch[1:])):
            issues.append("چپترها نامعتبرند (۰:۰۰ اول، دست‌کم ۳ تا، هر کدام ۱۰ ثانیه)؛ با yt-chapters بررسی کن")
        else:
            good.append(f"{len(ch)} چپتر معتبر")
    else:
        notes.append("چپتر ندارد؛ برای ویدیوی بالای ۵ دقیقه معمولاً ارزش دارد (yt-chapters)")

    tag_list = [t.strip() for t in re.split(r"[,،\n]", tags or "") if t.strip()]
    total = sum(len(t) for t in tag_list) + max(0, len(tag_list) - 1)
    if total > TAGS_MAX:
        issues.append(f"تگ‌ها {total} حرف‌اند؛ سقف یوتیوب {TAGS_MAX} حرف است")
    dup = {t for t in tag_list if [low(x) for x in tag_list].count(low(t)) > 1}
    if dup:
        issues.append(f"تگ تکراری: {'، '.join(sorted(dup))}")
    if tag_list:
        notes.append("تگ‌ها اثر کمی دارند؛ بیشترشان را برای غلط‌های املایی رایج و نوشتن فینگلیش اسم موضوع بگذار")

    hashes = re.findall(r"(?:^|\s)(#[\w" + ZWNJ + r"_]+)", desc)
    if len(hashes) > HASH_MAX:
        issues.append(f"{len(hashes)} هشتگ؛ بیش از {HASH_MAX} تا یعنی یوتیوب همه را نادیده می‌گیرد")
    elif hashes:
        notes.append(f"سه هشتگ اول بالای عنوان نشان داده می‌شود: {' '.join(hashes[:3])}")
    if SHORTENERS.search(desc):
        issues.append("لینک کوتاه‌شده؛ بیننده نمی‌داند کجا می‌رود. لینک کامل بگذار")
    score = max(0, 100 - 12 * len(issues))
    return {"score": score, "fold_preview": fold, "issues": issues, "good": good, "notes": notes,
            "tags_chars": total, "hashtags": hashes[:10], "chapters": len(ch)}


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="بررسی توضیحات و تگ‌های یوتیوب")
    ap.add_argument("--title", default="")
    ap.add_argument("--desc", required=True, help="فایل متن توضیحات")
    ap.add_argument("--tags", default="", help="تگ‌ها با ویرگول، یا مسیر فایل")
    ap.add_argument("--queries", default="", help="کوئری‌های هدف با | جدا شده")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    desc = open(a.desc, encoding="utf-8").read() if os.path.exists(a.desc) else a.desc
    tags = open(a.tags, encoding="utf-8").read() if a.tags and os.path.exists(a.tags) else a.tags
    queries = [q.strip() for q in a.queries.split("|") if q.strip()]
    r = check(a.title, desc, tags, queries)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    print(f"\n  امتیاز {r['score']}/۱۰۰")
    print(f"  پیش از «بیشتر» دیده می‌شود: «{r['fold_preview'].strip()}…»")
    for m in r["issues"]:
        print(f"    ✗ {m}")
    for m in r["good"]:
        print(f"    ✓ {m}")
    for m in r["notes"]:
        print(f"    · {m}")
    print()


if __name__ == "__main__":
    main()
