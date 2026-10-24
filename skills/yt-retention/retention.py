#!/usr/bin/env python3
"""
retention.py - خواندن خروجی «ماندگاری مخاطب» (Audience retention) یوتیوب استودیو و پیدا کردن نشت‌ها.

بر پایهٔ retention.py از youtube-agent-skill (Jake Schincariol, MIT)، بازنویسی‌شده برای فارسی.

  python retention.py retention.csv --duration 600
  python retention.py retention.csv --duration 600 --transcript transcript.srt   # می‌گوید سر هر ریزش چه می‌گفتی
  python retention.py retention.csv --json

گرفتن فایل از استودیو: Analytics ← یک ویدیو ← Engagement (تعامل) ← نمودار ماندگاری مخاطب ← آیکن دانلود.
دو ستون لازم است: موقعیت در ویدیو (درصد یا ثانیه) و درصدی که هنوز تماشا می‌کنند. ستون‌های فارسی،
رقم فارسی، «٪» و ممیز «٫» هم خوانده می‌شود. اگر محور درصد است، `--duration` (ثانیه یا «10:05») بده
تا زمان دقیق ریزش‌ها معلوم شود.

سه چیز گزارش می‌دهد، چون سه مشکل جدا با سه درمان جدا هستند:
  نشت قلاب   آنچه در ۳۰ ثانیهٔ اول از دست رفته
  پرتگاه‌ها  افت‌های تند تکی؛ لحظهٔ مشخصی که مردم رفتند
  سُرخوردن   نرخ ریزش یکنواخت در میانهٔ ویدیو
"""

import argparse
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import setup_stdout, to_en_digits, load_transcript, parse_ts, mmss  # noqa: E402


def cell_num(c):
    c = to_en_digits(c).strip().replace("%", "").replace("٪", "").replace("٫", ".").replace("٬", "")
    c = c.replace(",", "")
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", c):
        return parse_ts(c)
    try:
        return float(c)
    except ValueError:
        return None


def load_csv(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        sample = fh.read(2048)
        fh.seek(0)
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
        for r in csv.reader(fh, delimiter=delim):
            vals = [n for n in (cell_num(c) for c in r) if n is not None]
            if len(vals) >= 2:
                rows.append((vals[0], vals[1]))
    # بعضی خروجی‌ها کسر (۰ تا ۱) می‌دهند نه درصد
    if rows and max(y for _, y in rows) <= 1.5:
        rows = [(x, y * 100) for x, y in rows]
    return rows


def analyse(rows, dur=None, axis="auto"):
    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    if axis == "auto":
        # محور درصد تا ۱۰۰ می‌رود؛ اگر مدت ویدیو را داریم و آخرین نقطه نزدیک همان مدت است، محور ثانیه است.
        pct_axis = max(xs) <= 100.5 and not (dur and abs(max(xs) - dur) < 0.1 * dur and dur <= 100.5)
    else:
        pct_axis = axis == "percent"

    def at(x):
        return (x / 100.0 * dur) if (pct_axis and dur) else (x if not pct_axis else None)

    start = ys[0] or 100.0
    cutoff = 30.0 if not pct_axis else (30.0 / dur * 100 if dur else 10.0)
    hook_end = min((y for x, y in rows if x <= cutoff), default=start)
    hook_leak = start - hook_end
    drops = []
    for i in range(1, len(rows)):
        d = ys[i - 1] - ys[i]
        span = (xs[i] - xs[i - 1]) or 1
        drops.append((d / span, xs[i - 1], xs[i], d))
    steep = sorted(drops, reverse=True)
    cliffs = [{"from": round(a1, 2), "to": round(b1, 2), "lost": round(d, 2),
               "at_seconds": (round(at(a1), 1) if at(a1) is not None else None)}
              for _, a1, b1, d in [x for x in steep if x[3] > 0.8 and x[1] >= cutoff * 0.5][:5]]
    cliffs.sort(key=lambda c: c["from"])
    mid = [r[0] for r in drops if r[1] > cutoff]
    # میانه، تا پرتگاه‌ها نرخ سُرخوردن را بالا نبرند
    slide = sorted(mid)[len(mid) // 2] if mid else 0
    unit = "در هر ۱٪ ویدیو" if pct_axis else "در هر ثانیه"
    return {"points": len(rows), "start": round(start, 1), "end": round(ys[-1], 1),
            "pct_axis": pct_axis, "duration": dur, "hook_leak": round(hook_leak, 1),
            "hook_verdict": "سالم" if hook_leak < 25 else ("نشتی" if hook_leak < 40 else "شدید"),
            "cliffs": cliffs, "slide": round(slide, 3), "slide_unit": unit}


def parse_duration(s):
    if s is None:
        return None
    s = to_en_digits(str(s))
    return parse_ts(s) if ":" in s else float(s)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="تحلیل ماندگاری مخاطب یوتیوب")
    ap.add_argument("csv")
    ap.add_argument("--duration", help="مدت ویدیو: ثانیه یا «10:05»")
    ap.add_argument("--transcript", help="زیرنویس SRT/VTT/JSON برای دیدن حرف سر هر ریزش")
    ap.add_argument("--axis", choices=("auto", "percent", "seconds"), default="auto",
                    help="محور افقی فایل؛ پیش‌فرض خودکار")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.csv):
        print(f"فایل پیدا نشد: {a.csv}")
        sys.exit(1)
    rows = load_csv(a.csv)
    if len(rows) < 8:
        print("از این فایل دست‌کم ۸ نقطهٔ داده خوانده نشد؛ فایل «Audience retention» استودیو است؟")
        sys.exit(1)
    r = analyse(rows, parse_duration(a.duration), a.axis)
    said = {}
    if a.transcript and os.path.exists(a.transcript):
        cues = load_transcript(a.transcript)
        for c in r["cliffs"]:
            if c["at_seconds"] is None:
                continue
            t = c["at_seconds"]
            near = [q[2] for q in cues if q[0] <= t + 4 and q[1] >= t - 4]
            c["said"] = " ".join(near)[:160]
            said[t] = c["said"]
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    print(f"\n  {a.csv}   {r['points']} نقطه   {r['start']:.1f}٪ ← {r['end']:.1f}٪\n")
    print(f"  نشت قلاب   {r['hook_leak']:.1f}٪ در شروع ویدیو رفتند   [{r['hook_verdict']}]")
    print("             زیر ۲۵٪ سالم است. پیش از هر چیز، جملهٔ اول را درست کن (yt-script).\n")
    print("  پرتگاه‌ها  لحظه‌هایی که مردم واقعاً رفتند")
    for c in r["cliffs"]:
        where = mmss(c["at_seconds"]) if c["at_seconds"] is not None else f"{c['from']}٪ ویدیو"
        print(f"    -{c['lost']:5.1f}٪  در {where:>8}" + (f"   «{c['said']}»" if c.get("said") else ""))
    if not r["cliffs"]:
        print("    هیچ افتی تندتر از ۰٫۸٪ نیست؛ ریزش همه‌اش سُرخوردن است، نه لحظه")
    if r["pct_axis"] and not r["duration"]:
        print("    (برای زمان دقیق، --duration را بده)")
    print(f"\n  سُرخوردن   {r['slide']:.3f}٪ {r['slide_unit']} در میانهٔ ویدیو")
    print("             سُرخوردن یکنواخت یعنی ریتم، نه محتوا. میانه را کوتاه کن، بازنویسی‌اش نکن.\n")


if __name__ == "__main__":
    main()
