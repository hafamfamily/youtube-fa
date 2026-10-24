#!/usr/bin/env python3
"""
shorts.py - پیدا کردن شورتس‌های پنهان در یک ویدیوی بلند، از روی زیرنویس زمان‌دار فارسی.

ابزار تازهٔ youtube-fa (در نسخهٔ اصلی youtube-agent-skill این مرحله فقط دستورالعمل بود).

پنجره‌هایی بین ۲۰ تا ۵۸ ثانیه را می‌سنجد که:
  - از ابتدای یک جمله و بعد از یک مکث شروع می‌شوند (برش تمیز)،
  - با یک مکث تمام می‌شوند (پایان تمیز)،
  - به جملهٔ قبل از خودشان تکیه نکرده‌اند («همین»، «اون»، «پس»، «که گفتم» در شروع = وابسته)،
  - جملهٔ اولشان خودش قلاب است (با hookscore از yt-script سنجیده می‌شود)،
  - و چیز مشخصی دارند (عدد، اسم، هشدار).

خروجی پیش‌نویس است: زمان شروع و پایان، جملهٔ اول فعلی و امتیازش. جملهٔ اول تازه را yt-shorts می‌نویسد.

  python shorts.py transcript.srt
  python shorts.py transcript.srt --top 5 --min 20 --max 58 --json
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import setup_stdout, load_transcript, mmss, numbers, latin_names, normalize  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(HERE), "yt-script"))
try:
    import hookscore  # noqa: E402
except Exception:
    hookscore = None

DEPENDENT = re.compile(r"^\s*(?:همین|همون|اون|این(?:و|ها)?|پس|که|و |ولی|اما|بعدش|بعد|یعنی|درنتیجه|"
                       r"همون‌طور که|همونطور که|که گفتم|گفتم|دوباره|دومی|سومی|حالا)\b")
PAUSE = 0.35


def windows(cues, lo, hi):
    n = len(cues)
    for i in range(n):
        gap_before = cues[i][0] - cues[i - 1][1] if i else 1.0
        if gap_before < PAUSE and i:
            continue
        for j in range(i, n):
            length = cues[j][1] - cues[i][0]
            if length > hi:
                break
            if length < lo:
                continue
            gap_after = cues[j + 1][0] - cues[j][1] if j + 1 < n else 1.0
            if gap_after < PAUSE and j + 1 < n:
                continue
            yield i, j, gap_before, gap_after


def score_window(cues, i, j, gb, ga):
    text = " ".join(c[2] for c in cues[i:j + 1])
    first = cues[i][2]
    hs = hookscore.score(first) if hookscore else None
    s = (hs["score"] if hs else 50) * 0.6
    s += min(20, 6 * (len(numbers(text)) + len(latin_names(text))))
    s += min(10, gb * 6) + min(10, ga * 6)
    dep = bool(DEPENDENT.match(normalize(first)))
    if dep:
        s -= 25
    length = cues[j][1] - cues[i][0]
    if 25 <= length <= 45:
        s += 8
    return {"start": round(cues[i][0], 2), "end": round(cues[j][1], 2), "length": round(length, 1),
            "from": mmss(cues[i][0]), "to": mmss(cues[j][1]), "first_line": first,
            "hook": hs["score"] if hs else None, "formula": hs["formula"] if hs else None,
            "dependent": dep, "score": round(s), "text": text}


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="پیدا کردن شورتس در ویدیوی بلند")
    ap.add_argument("transcript")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--min", type=float, default=20)
    ap.add_argument("--max", type=float, default=58)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.transcript):
        print(f"فایل پیدا نشد: {a.transcript}")
        sys.exit(1)
    cues = load_transcript(a.transcript)
    if not cues:
        print("هیچ تکهٔ زمان‌داری پیدا نشد.")
        sys.exit(1)
    cands = sorted((score_window(cues, *w) for w in windows(cues, a.min, a.max)), key=lambda r: -r["score"])
    picked = []
    for c in cands:
        if all(c["end"] <= p["start"] or c["start"] >= p["end"] for p in picked):
            picked.append(c)
        if len(picked) >= a.top:
            break
    if a.json:
        print(json.dumps(picked, ensure_ascii=False, indent=1))
        return
    if not picked:
        print("\n  هیچ تکهٔ مستقلی بین", a.min, "و", a.max, "ثانیه پیدا نشد؛ مکث‌های بین بخش‌ها کوتاه است.\n")
        return
    print(f"\n  {len(picked)} شورتس پیشنهادی از {a.transcript}\n")
    for n, c in enumerate(picked, 1):
        print(f"  {n}. {c['from']} ← {c['to']}  ({c['length']} ثانیه)  امتیاز {c['score']}")
        print(f"     جملهٔ اول فعلی: «{c['first_line']}»" +
              (f"  [قلاب {c['hook']}، {c['formula'] or 'بی‌فرمول'}]" if c["hook"] is not None else ""))
        if c["dependent"]:
            print("     ⚠ به حرف قبلی تکیه دارد؛ جملهٔ اول باید تازه نوشته یا ضبط شود")
    print("\n  برای هر کدام یک جملهٔ اول تازه بنویس؛ جملهٔ اول ویدیوی بلند تقریباً هیچ‌وقت قلاب شورتس نیست.\n")


if __name__ == "__main__":
    main()
