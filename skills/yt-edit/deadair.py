#!/usr/bin/env python3
"""
deadair.py - فهرست برش تدوین (EDL) از روی زیرنویس زمان‌دار؛ برای گفتار فارسی.

بر پایهٔ deadair.py از youtube-agent-skill (Jake Schincariol, MIT)، بازنویسی‌شده برای فارسی.

  python deadair.py transcript.srt              # یا .vtt یا JSON خروجی Whisper
  python deadair.py transcript.srt --floor 0.35 --json
  python deadair.py transcript.srt --csv cuts.csv   # فهرست برش برای وارد کردن در جدول یا نرم‌افزار

سه چیز پیدا می‌کند:
  سکوت     فاصلهٔ بین دو جملهٔ گفته‌شده، بیشتر از آستانه (پیش‌فرض ۰٫۴۵ ثانیه)
  پرکننده  تکه‌ای که فقط تکیه‌کلام است: «اِم»، «اِ»، «خب»، «یعنی»، «چیزه»، «ببین»، «درواقع»...
  تکرار    جمله‌ای که دوباره شروع شده؛ برداشت اول حذف می‌شود و دومی می‌ماند

و جدا از این‌ها، شمارش تکیه‌کلام‌هایی را که وسط جمله‌ها آمده گزارش می‌دهد (برای ضبط بعدی).

این چه نمی‌کند: فایل را نمی‌بُرد. فهرست برش، مجموع حذف و مدت نهایی را می‌دهد و تو در هر نرم‌افزار
تدوینی که داری اعمالش می‌کنی. به هیچ فایل صوتی یا تصویری دست نمی‌زند.

زیرنویس فارسی زمان‌دار: خروجی Whisper (مثلاً با برنامه‌های رایگان مثل Subtitle Edit یا
whisper.cpp)، یا زیرنویس خودکار یوتیوب استودیو.
"""

import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import setup_stdout, normalize, ZWNJ, load_transcript  # noqa: E402

# تکیه‌کلام‌های فارسی گفتاری؛ «یعنی» و «خب» وقتی تنها می‌آیند پرکننده‌اند، وسط جمله نه همیشه.
FILLERS = [
    "اِم", "ام", "اممم", "امم", "اِ", "اه", "ااا", "آآ", "اوم", "هوم", "مم", "ممم", "خب", "خوب",
    "یعنی", "چیزه", "چیز", "ببین", "ببینید", "درواقع", "در واقع", "به‌هرحال", "بهرحال", "به هر حال",
    "مثلاً", "مثلا", "حالا", "دیگه", "اصلاً", "اصلا", "کلاً", "کلا", "راستش", "آره", "باشه",
    "بذار ببینم", "بزار ببینم", "یه لحظه", "چی بگم", "عرضم به حضورتون", "عرض کنم", "یعنی چی",
    "um", "uh", "so", "okay", "ok", "like", "you know",
]
_alt = "|".join(sorted((re.escape(f).replace(r"\ ", r"\s") for f in FILLERS), key=len, reverse=True))
FILLER_ONLY = re.compile(r"^[\s,،.…\-]*(?:(?:" + _alt + r")[\s,،.…\-]*)+$", re.I)
FILLER_WORD = re.compile(r"(?:(?<=\s)|^)(?:اِم|اممم|امم|اِ|ااا|اوم|هوم|ممم|چیزه|درواقع|در واقع|"
                         r"به‌هرحال|بهرحال|یعنی|مثلاً|مثلا|راستش|عرضم به حضورتون)(?=[\s,،.…]|$)")


load = load_transcript


def norm_words(t):
    t = normalize(t).replace(ZWNJ, "")
    return re.findall(r"[؀-ۿa-zA-Z0-9۰-۹]+", t.lower())


def tc(sec):
    sec = max(0.0, sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


KIND_FA = {"DEAD": "سکوت", "FILLER": "پرکننده", "REPEAT": "تکرار"}


def analyse(cues, floor):
    dur = cues[-1][1]
    cuts = []
    for i, (s, e, t) in enumerate(cues):
        if FILLER_ONLY.match(t):
            cuts.append({"kind": "FILLER", "start": s, "end": e, "why": t.strip()[:48]})
        if i:
            gap = s - cues[i - 1][1]
            if gap > floor:
                keep = floor / 2
                cuts.append({"kind": "DEAD", "start": round(cues[i - 1][1] + keep, 3),
                             "end": round(s - keep, 3), "why": f"{gap:.2f} ثانیه مکث"})
        # تکرار با آخرین تکهٔ «گفتاری» مقایسه می‌شود؛ معمولاً بین دو برداشت یک «اِم» هست.
        if t.strip() and not FILLER_ONLY.match(t):
            j = i - 1
            while j >= 0 and (FILLER_ONLY.match(cues[j][2]) or not cues[j][2].strip()):
                j -= 1
            if j >= 0:
                a1, b1 = norm_words(cues[j][2])[:4], norm_words(t)[:4]
                if len(a1) >= 3 and a1 == b1:
                    cuts.append({"kind": "REPEAT", "start": cues[j][0], "end": cues[j][1],
                                 "why": f"شروع دوباره: «{' '.join(a1)}»"})
    cuts = [c for c in cuts if c["end"] > c["start"]]
    cuts.sort(key=lambda c: c["start"])
    # هم‌پوشانی‌ها را یکی کن تا مجموع حذف دو بار شمرده نشود.
    merged = []
    for c in cuts:
        if merged and c["start"] <= merged[-1]["end"]:
            m = merged[-1]
            m["end"] = max(m["end"], c["end"])
            if c["kind"] not in m["kind"]:
                m["kind"] += "+" + c["kind"]
                m["why"] += "؛ " + c["why"]
        else:
            merged.append(dict(c))
    removed = sum(c["end"] - c["start"] for c in merged)
    tics = {}
    for _, _, t in cues:
        if FILLER_ONLY.match(t):
            continue
        for m in FILLER_WORD.findall(" " + t):
            k = m.strip()
            tics[k] = tics.get(k, 0) + 1
    return {"duration": round(dur, 3), "cues": len(cues), "cuts": merged,
            "removed": round(removed, 3), "out": round(dur - removed, 3),
            "tics": dict(sorted(tics.items(), key=lambda x: -x[1]))}


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="فهرست برش تدوین از زیرنویس فارسی")
    ap.add_argument("transcript")
    ap.add_argument("--floor", type=float, default=0.45, help="آستانهٔ سکوت به ثانیه")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--csv", help="ذخیرهٔ فهرست برش در CSV")
    a = ap.parse_args()
    if not os.path.exists(a.transcript):
        print(f"فایل پیدا نشد: {a.transcript}")
        sys.exit(1)
    cues = load(a.transcript)
    if not cues:
        print("هیچ تکهٔ زمان‌داری پیدا نشد؛ فایل SRT، VTT یا JSON خروجی Whisper است؟")
        sys.exit(1)
    r = analyse(cues, a.floor)
    r["source"] = a.transcript
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["نوع", "شروع", "پایان", "مدت (ثانیه)", "دلیل"])
            for c in r["cuts"]:
                w.writerow([c["kind"], tc(c["start"]), tc(c["end"]), round(c["end"] - c["start"], 2), c["why"]])
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    d = r["duration"]
    print(f"\n  {a.transcript}   مدت {d:.1f} ثانیه، {r['cues']} تکه، آستانهٔ سکوت {a.floor} ثانیه\n")
    for c in r["cuts"]:
        kind = "+".join(KIND_FA.get(k, k) for k in c["kind"].split("+"))
        print(f"    {kind:<14} {tc(c['start'])} ← {tc(c['end'])}   {c['end'] - c['start']:5.2f}s   {c['why']}")
    pct = r["removed"] / d * 100 if d else 0
    print(f"\n  {len(r['cuts'])} برش، {r['removed']:.1f} ثانیه حذف، مدت نهایی {r['out']:.1f} ثانیه "
          f"({pct:.1f}٪ کوتاه‌تر)")
    if r["tics"]:
        top = "، ".join(f"«{k}» {v} بار" for k, v in list(r["tics"].items())[:5])
        print(f"  تکیه‌کلام وسط جمله‌ها (برای ضبط بعدی): {top}")
    if a.csv:
        print(f"  فهرست برش: {a.csv}")
    print()


if __name__ == "__main__":
    main()
