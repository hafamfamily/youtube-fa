#!/usr/bin/env python3
"""
title.py - بررسی عنوان و متن تامبنیل یوتیوب به‌عنوان یک جفت، پیش از انتشار.

بر پایهٔ title.py از youtube-agent-skill (Jake Schincariol, MIT)، بازنویسی‌شده برای فارسی.

واحد کار «جفت» است، نه عنوان. عنوانی که متن تامبنیل را تکرار کند نصف سطح کلیک را هدر داده؛
رایج‌ترین اشتباهی که این ابزار پیدا می‌کند همین است.

طول: یوتیوب در جست‌وجوی دسکتاپ حدود ۶۰ حرف و در صفحهٔ اصلی موبایل حدود ۴۰ حرف را نشان می‌دهد؛
سقف قطعی ۱۰۰ حرف است. طول «دیداری» شمرده می‌شود (نیم‌فاصله حرف حساب نمی‌شود).

  python title.py --title "..." --thumb "متن تامبنیل"
  python title.py titles.txt [--thumb "..."]       # هر خط یک عنوان، رتبه‌بندی
  python title.py --title "..." --json
  python title.py --title "..." --max-thumb-words 3
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import setup_stdout, words, low, numbers, latin_names, visible_len, EMOJI_RE, ZWNJ  # noqa: E402

DESKTOP, MOBILE, HARD = 60, 40, 100

VAGUE = {
    "فوق‌العاده", "فوقالعاده", "باورنکردنی", "شگفت‌انگیز", "خفن", "جادویی", "انقلابی", "بی‌نظیر",
    "عالی", "وحشتناک", "دیوانه‌کننده", "معجزه", "کامل", "جامع", "همه‌چیز", "همه‌چی", "قدرتمند",
    "نهایی", "حرفه‌ای", "بهترین", "مهم", "جالب", "عجیب", "باحال", "epic", "ultimate", "best",
}
CLICKBAIT = re.compile(
    r"(?:باورتون نمی‌?شه|باورت نمی‌?شه|حتماً? ببینید|حتما ببین|فوری|فوووری|شوکه|"
    r"جنجالی|فاش شد|افشا|نبینی ضرر|از دستش نده|اشکتون|تا آخر ببینید|دیدنی)")
STOP = {
    "و", "در", "به", "از", "که", "را", "رو", "با", "برای", "این", "اون", "آن", "یه", "یک", "تا",
    "هم", "چه", "چی", "چرا", "چطور", "چطوری", "من", "تو", "شما", "ما", "است", "هست", "بود",
    "می", "کن", "کرد", "کردم", "شد", "کنی", "کنید", "دیگه", "هر", "همه", "بدون",
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "you", "your", "my", "i",
}
SPOKEN_NUMBERS = {"دو", "سه", "چهار", "پنج", "شش", "هفت", "هشت", "نه", "ده", "بیست", "سی", "صد",
                  "هزار", "میلیون", "میلیارد", "نصف", "دوبرابر"}
FA_DIGIT = re.compile(r"[۰-۹٠-٩]")
EN_DIGIT = re.compile(r"[0-9]")
SUFFIX = re.compile(r"(?:" + ZWNJ + r")?(?:هایی|های|ها|ای|ی|ات|تون|ت|مون|م|شون|ش)$")


def stem(w):
    """ریشهٔ ساده برای مقایسهٔ عنوان و تامبنیل: «میکروفون‌ها» = «میکروفون»."""
    w = low(w).replace(ZWNJ, "")
    if len(w) > 4:
        w2 = SUFFIX.sub("", w)
        if len(w2) >= 3:
            w = w2
    return w


def content(text):
    return {stem(w) for w in words(text) if low(w) not in STOP and len(low(w)) > 1}


def check(title, thumb=None, max_thumb=4):
    t = title.strip()
    n = visible_len(t)
    issues, good, notes = [], [], []

    if n > HARD:
        issues.append(("طول", f"{n} حرف؛ سقف قطعی یوتیوب {HARD} حرف است"))
    elif n > DESKTOP:
        issues.append(("طول", f"{n} حرف؛ جست‌وجوی دسکتاپ نزدیک {DESKTOP} حرف بریده می‌شود"))
    else:
        good.append(f"{n} حرف، داخل برش {DESKTOP} حرفی دسکتاپ")
    if n > MOBILE:
        cut, count = "", 0
        for ch in t:
            if ch != ZWNJ:
                count += 1
            if count > MOBILE:
                break
            cut += ch
        head = cut.rsplit(" ", 1)[0] if " " in cut else cut
        notes.append(f"موبایل حدوداً «{head}…» را نشان می‌دهد؛ موضوع اصلی باید در همین تکه باشد")

    v = sorted({low(w) for w in words(t) if low(w) in VAGUE})
    if v:
        issues.append(("کلی‌گویی", f"{'، '.join(v)}؛ با یک عدد، اسم یا تاریخ عوضش کن"))
    cb = CLICKBAIT.findall(t)
    if cb:
        issues.append(("کلیک‌بیت", f"«{cb[0]}»؛ بینندهٔ فارسی‌زبان این عبارت‌ها را می‌شناسد و به آن اعتماد نمی‌کند"))
    bangs = len(re.findall(r"[!！]", t)) + len(re.findall(r"[?؟]{2,}", t))
    if bangs > 1:
        issues.append(("علامت", "چند علامت تعجب یا سؤال پشت سر هم؛ یکی بس است"))
    emo = EMOJI_RE.findall(t)
    if len(emo) > 1:
        issues.append(("ایموجی", f"{len(emo)} ایموجی؛ حداکثر یکی"))
    caps = [w for w in t.split() if len(w) > 2 and w.isascii() and w.isupper()]
    if len(caps) > 2:
        issues.append(("داد زدن", f"{len(caps)} کلمهٔ لاتین تمام‌بزرگ"))

    nums = numbers(t)
    spoken = [low(w) for w in words(t) if low(w) in SPOKEN_NUMBERS]
    names = latin_names(t)
    if nums or spoken:
        good.append(f"عدد مشخص دارد ({'، '.join((nums + spoken)[:3])})")
    elif names:
        good.append(f"اسم مشخص دارد ({'، '.join(names[:2])})")
    else:
        issues.append(("بی‌عدد", "نه عدد، نه تاریخ، نه اسم؛ مطمئن‌ترین اصلاح تکی"))
    if FA_DIGIT.search(t) and EN_DIGIT.search(t):
        notes.append("رقم فارسی و لاتین با هم آمده؛ یکی را انتخاب کن تا یکدست باشد")
    if re.search(r"[?؟]\s*$", t):
        good.append("سؤال باز در عنوان")

    front = [w for w in words(t)[:3] if low(w) not in STOP]
    if not front:
        issues.append(("جلوبودن", "سه کلمهٔ اول همه پرکننده‌اند؛ موضوع را جلو بیاور"))
    first = t.split()[0] if t.split() else ""
    if first and (first[0].isascii() and first[0].isalnum()) and re.search(r"[؀-ۿ]", t):
        notes.append("عنوان فارسی با کلمه یا عدد لاتین شروع شده؛ در بعضی نمایش‌ها ترتیب کلمه‌ها به‌هم می‌ریزد. پیش‌نمایش را ببین")

    if thumb:
        shared = content(t) & content(thumb)
        if shared:
            issues.append(("تکرار", f"تامبنیل کلمهٔ «{'، '.join(sorted(shared))}» عنوان را تکرار کرده؛ "
                                     "تامبنیل باید چیزی بگوید که عنوان نمی‌گوید"))
        else:
            good.append("عنوان و تامبنیل کلمه‌های متفاوت دارند")
        tw = len(words(thumb))
        if tw > max_thumb:
            issues.append(("تامبنیل", f"{tw} کلمه روی تامبنیل؛ در اندازهٔ فید بیش از {max_thumb} کلمه خوانده نمی‌شود"))
        if visible_len(thumb) > 24:
            notes.append(f"متن تامبنیل {visible_len(thumb)} حرف است؛ با فونت درشت فارسی معمولاً بیش از ۲۰ حرف جا نمی‌شود")

    score = max(0, min(100, 100 - 14 * len(issues) + 4 * len(good)))
    return {"title": t, "thumb": thumb, "chars": n, "score": score,
            "issues": issues, "good": good, "notes": notes}


def show(r):
    print(f"\n  «{r['title']}»" + (f"   +   تامبنیل: «{r['thumb']}»" if r["thumb"] else ""))
    print(f"  {r['chars']} حرف   امتیاز {r['score']}/۱۰۰")
    for k, m in r["issues"]:
        print(f"    ✗  {k:<9} {m}")
    for m in r["good"]:
        print(f"    ✓  {'':<9} {m}")
    for m in r["notes"]:
        print(f"    ·  {'':<9} {m}")


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="بررسی عنوان و تامبنیل یوتیوب")
    ap.add_argument("input", nargs="?", help="فایل: هر خط یک عنوان (یا «عنوان | متن تامبنیل»)")
    ap.add_argument("--title")
    ap.add_argument("--thumb")
    ap.add_argument("--max-thumb-words", type=int, default=4)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.title:
        rows = [check(a.title, a.thumb, a.max_thumb_words)]
    elif a.input and os.path.exists(a.input):
        rows = []
        for line in open(a.input, encoding="utf-8").read().splitlines():
            if not line.strip():
                continue
            ti, _, th = line.partition("|")
            rows.append(check(ti, th.strip() or a.thumb, a.max_thumb_words))
    else:
        ap.print_help()
        sys.exit(1)
    rows.sort(key=lambda r: -r["score"])
    if a.json:
        print(json.dumps(rows if len(rows) > 1 else rows[0], ensure_ascii=False, indent=1))
        return
    for r in rows:
        show(r)
    print()


if __name__ == "__main__":
    main()
