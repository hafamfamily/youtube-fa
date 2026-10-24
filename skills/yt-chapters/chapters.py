#!/usr/bin/env python3
"""
chapters.py - چپترهای یوتیوب از روی زیرنویس زمان‌دار فارسی.

بر پایهٔ chapters.py از youtube-agent-skill (Jake Schincariol, MIT)، بازنویسی‌شده برای فارسی.

  python chapters.py transcript.srt                 # یا .vtt یا JSON خروجی Whisper
  python chapters.py transcript.srt --target 8 --json
  python chapters.py --check description.txt        # بررسی چپترهایی که خودت نوشته‌ای

قواعد خود یوتیوب، که اینجا بررسی می‌شود نه فرض: فهرست باید با 0:00 شروع شود، دست‌کم سه چپتر داشته
باشد، و هر چپتر دست‌کم ۱۰ ثانیه باشد. زمان‌ها به ترتیب صعودی. فهرستی که یکی از این‌ها را نقض کند،
بی‌صدا چپتر نمی‌شود؛ برای همین بررسی می‌کنیم.

زمان‌ها همیشه با رقم لاتین نوشته می‌شوند (0:00)، و هر خط با زمان شروع می‌شود و بعد عنوان فارسی؛
این ترتیب در متن راست‌به‌چپ هم درست خوانده می‌شود.

مرزها از مکث‌هایی می‌آیند که بین بخش‌ها کرده‌ای، به‌اضافهٔ اینکه کلمه‌های محتوایی چقدر قبل و بعد
از مکث عوض می‌شوند. خروجی پیش‌نویس است؛ عنوان‌ها کلمه‌های کلیدی‌اند و باید بازنویسی شوند.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import (setup_stdout, load_transcript, keywords, mmss, to_en_digits,  # noqa: E402
                     words, low, ZWNJ, parse_ts)

MIN = 10.0
LINE_RE = re.compile(r"^\s*\(?((?:\d{1,2}:)?\d{1,2}:\d{2})\)?\s*[-–—:]?\s*(.+?)\s*$")


def validate(chapters, duration=None):
    """chapters: فهرست (ثانیه، عنوان). خروجی: فهرست ایرادها (خالی یعنی درست)."""
    errs = []
    if len(chapters) < 3:
        errs.append(f"{len(chapters)} چپتر؛ یوتیوب دست‌کم ۳ تا لازم دارد")
    if not chapters or chapters[0][0] != 0:
        errs.append("چپتر اول باید دقیقاً 0:00 باشد")
    for i in range(1, len(chapters)):
        if chapters[i][0] <= chapters[i - 1][0]:
            errs.append(f"زمان {mmss(chapters[i][0])} از قبلی‌اش جلوتر نیست")
        elif chapters[i][0] - chapters[i - 1][0] < MIN:
            errs.append(f"چپتر «{chapters[i - 1][1]}» کمتر از ۱۰ ثانیه است")
    if duration and chapters and duration - chapters[-1][0] < MIN:
        errs.append(f"چپتر آخر «{chapters[-1][1]}» کمتر از ۱۰ ثانیه است")
    for t, title in chapters:
        if len(title.replace(ZWNJ, "")) > 40:
            errs.append(f"عنوان «{title[:30]}…» بلند است؛ زیر ۴۰ حرف نگهش دار")
    return errs


def from_transcript(cues, target):
    dur = cues[-1][1]
    cand = []
    for i in range(1, len(cues)):
        gap = cues[i][0] - cues[i - 1][1]
        before = " ".join(c[2] for c in cues[max(0, i - 12):i])
        after = " ".join(c[2] for c in cues[i:i + 12])
        kb, ka = keywords(before), keywords(after)
        shift = 1 - (len(kb & ka) / len(kb | ka)) if (kb | ka) else 0
        cand.append((gap * 1.6 + shift * 3.2, cues[i][0], i))
    cand.sort(reverse=True)
    picked = [0.0]
    for _, t, _i in cand:
        if len(picked) >= target:
            break
        if all(abs(t - p) >= MIN for p in picked) and dur - t >= MIN:
            picked.append(t)
    picked.sort()
    chapters = []
    for n, t in enumerate(picked):
        end = picked[n + 1] if n + 1 < len(picked) else dur
        text = " ".join(c[2] for c in cues if c[0] >= t and c[1] <= end + 0.01)
        counts = {}
        for w in words(text):
            k = low(w).replace(ZWNJ, "")
            if k in keywords(w):
                counts[k] = counts.get(k, 0) + 1
        kw = sorted(counts, key=lambda k: -counts[k])
        title = "مقدمه" if t == 0 and n == 0 and end <= 20 else (" ".join(kw[:3]) or "بخش")
        chapters.append({"start": round(t, 2), "label": mmss(t), "draft_title": title,
                         "seconds": round(end - t, 2)})
    return chapters, dur


def parse_block(text):
    out = []
    for line in text.splitlines():
        m = LINE_RE.match(to_en_digits(line))
        if m:
            out.append((int(parse_ts(m.group(1))), m.group(2)))
    return out


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="چپتر یوتیوب از زیرنویس فارسی")
    ap.add_argument("transcript", nargs="?")
    ap.add_argument("--target", type=int, default=7, help="حداکثر تعداد چپتر")
    ap.add_argument("--check", help="فایل متنی توضیحات/چپترها برای بررسی")
    ap.add_argument("--duration", type=float, help="مدت ویدیو به ثانیه (برای بررسی چپتر آخر)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if a.check:
        ch = parse_block(open(a.check, encoding="utf-8").read())
        errs = validate(ch, a.duration)
        if a.json:
            print(json.dumps({"valid": not errs, "chapters": ch, "errors": errs}, ensure_ascii=False, indent=1))
            return
        print(f"\n  {len(ch)} خط زمان‌دار پیدا شد.")
        for e in errs:
            print(f"    ✗ {e}")
        print("  ✓ درست است؛ یوتیوب آن را چپتر می‌کند.\n" if not errs else "")
        sys.exit(0 if not errs else 1)

    if not a.transcript or not os.path.exists(a.transcript):
        ap.print_help()
        sys.exit(1)
    cues = load_transcript(a.transcript)
    if len(cues) < 6:
        print("تکه‌های زیرنویس برای چپتر کم است (کمتر از ۶).")
        sys.exit(1)
    chapters, dur = from_transcript(cues, a.target)
    errs = validate([(c["start"], c["draft_title"]) for c in chapters], dur)
    if a.json:
        print(json.dumps({"valid": not errs, "errors": errs, "chapters": chapters},
                         ensure_ascii=False, indent=1))
        return
    print()
    for c in chapters:
        print(f"  {c['label']} {c['draft_title']}")
    print(f"\n  {len(chapters)} چپتر" + ("" if not errs else "  — نامعتبر: " + "؛ ".join(errs)))
    print("  پیش از چسباندن، همهٔ عنوان‌ها را بازنویسی کن؛ این‌ها کلمه‌های کلیدی‌اند، نه حرف تو.\n")


if __name__ == "__main__":
    main()
