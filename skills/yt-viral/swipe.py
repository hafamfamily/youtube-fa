#!/usr/bin/env python3
"""
swipe.py - رتبه‌بندی ویدیوهای جمع‌شده بر اساس «چند برابرِ میانهٔ خودِ همان کانال» و نام بردن فرمول عنوان.

بر پایهٔ swipe.py از youtube-agent-skill (Jake Schincariol, MIT)، بازنویسی‌شده برای فارسی.

چرا میانه؟ بازدید خام اندازهٔ کانال را رتبه‌بندی می‌کند، نه ایده را. ویدیوی ۴۰۰ هزاری در کانال
۲ میلیونی یک سه‌شنبهٔ معمولی است؛ همان عدد در کانالی که میانه‌اش ۳۰ هزار است، چیزی است که باید
مطالعه‌اش کرد. برای اینکه میانه معنا داشته باشد، از هر کانال دست‌کم ۴ ویدیو لازم است؛ کمتر از
آن را ابزار کنار می‌گذارد و می‌گوید.

ورودی (هر کدام):
  JSON:  [{"channel":"...","title":"...","views":412000,"url":"...","duration":613}, ...]
  خروجی yt-dlp:  yt-dlp --flat-playlist -J "<آدرس کانال>/videos" > ch1.json   (چند فایل هم می‌شود)
  TSV:   ستون‌های channel  title  views  [url  duration]
عددها می‌توانند فارسی یا لاتین باشند؛ «12K»، «1.2M»، «۱۲ هزار» هم قبول است.

فرمول از روی «عنوان» با فرمول‌های yt-script/hooks.json تشخیص داده می‌شود. این قضاوتی دربارهٔ
کلمه‌های روی صفحه است، نه ادعایی دربارهٔ اینکه چرا ویدیو دیده شد.

  python swipe.py collected.json --min 2.0
  python swipe.py ch1.json ch2.json ch3.json --out swipe.md
"""

import argparse
import csv
import json
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import setup_stdout, to_en_digits, normalize, mmss  # noqa: E402


def load_formulas():
    for p in (os.path.join(HERE, "..", "yt-script", "hooks.json"), os.path.join(HERE, "hooks.json")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)["hooks"]
    return []


FORMULAS = load_formulas()


def num(x):
    s = to_en_digits(str(x or 0)).strip().replace(",", "").replace("٬", "").replace("٫", ".").lower()
    mult = 1
    for suf, m in (("k", 1e3), ("هزار", 1e3), ("m", 1e6), ("میلیون", 1e6), ("b", 1e9)):
        if s.endswith(suf):
            mult, s = m, s[: -len(suf)].strip()
            break
    try:
        return float(s) * mult
    except ValueError:
        return 0.0


def classify(title):
    t = normalize(title)
    scored = []
    for f in FORMULAS:
        n = sum(1 for p in f["match"] if re.search(p, t, re.I))
        if n:
            scored.append((n, f["name"]))
    scored.sort(reverse=True)
    return scored[0][1] if scored else "دسته‌بندی‌نشده"


def read_file(path):
    if path.lower().endswith((".tsv", ".txt", ".csv")):
        with open(path, encoding="utf-8-sig") as f:
            delim = "\t" if path.lower().endswith((".tsv", ".txt")) else ","
            return list(csv.DictReader(f, delimiter=delim))
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    if isinstance(d, list):
        return d
    if isinstance(d, dict) and "entries" in d:  # yt-dlp
        ch = d.get("channel") or d.get("uploader") or d.get("title") or os.path.basename(path)
        out = []
        for e in d.get("entries") or []:
            if not e:
                continue
            out.append({"channel": e.get("channel") or e.get("uploader") or ch, "title": e.get("title", ""),
                        "views": e.get("view_count") or 0, "duration": e.get("duration"),
                        "url": e.get("url") or (f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else "")})
        return out
    return d.get("videos", []) if isinstance(d, dict) else []


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="رتبه‌بندی ویدیوها با ضریب میانهٔ کانال")
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--min", type=float, default=1.5, help="حداقل ضریب برای نمایش")
    ap.add_argument("--out", help="نوشتن فایل الهام (swipe.md)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = []
    for p in a.inputs:
        rows += read_file(p)
    by = {}
    for r in rows:
        by.setdefault(str(r.get("channel", "?")).strip(), []).append(r)
    out, thin = [], []
    for ch, vids in by.items():
        views = [num(v.get("views")) for v in vids]
        med = statistics.median(views) if views else 0
        if len(vids) < 4:
            thin.append((ch, len(vids)))
            continue
        for v in vids:
            m = num(v.get("views")) / med if med else 0
            dur = num(v.get("duration")) or None
            out.append({"channel": ch, "title": str(v.get("title", "")).strip(), "views": int(num(v.get("views"))),
                        "median": int(med), "multiple": round(m, 2), "duration": dur,
                        "formula": classify(str(v.get("title", ""))), "url": v.get("url", "")})
    hits = sorted((r for r in out if r["multiple"] >= a.min), key=lambda r: -r["multiple"])
    counts = {}
    for r in hits:
        counts[r["formula"]] = counts.get(r["formula"], 0) + 1
    if a.json:
        print(json.dumps({"outliers": hits, "skipped_thin_channels": thin, "formulas": counts},
                         ensure_ascii=False, indent=1))
        return

    lines = ["# فایل الهام یوتیوب (Swipe)\n",
             f"رتبه با «چند برابرِ میانهٔ همان کانال»؛ آستانه {a.min}×. الگو را برمی‌داریم، نه ویدیو را.",
             "فرمول، قضاوتی دربارهٔ کلمه‌های عنوان است؛ دلیل دیده شدن ویدیو نیست.\n",
             "| ضریب | بازدید | میانهٔ کانال | کانال | فرمول عنوان | مدت | عنوان |",
             "|---|---|---|---|---|---|---|"]
    for r in hits[:40]:
        d = mmss(r["duration"]) if r["duration"] else "-"
        t = f"[{r['title']}]({r['url']})" if r["url"] else r["title"]
        lines.append(f"| {r['multiple']:.1f}× | {r['views']:,} | {r['median']:,} | {r['channel']} | "
                     f"{r['formula']} | {d} | {t} |")
    if not hits:
        lines.append("\nهیچ ویدیویی از آستانه رد نشد؛ از هر کانال ویدیوی بیشتری جمع کن یا --min را پایین بیاور.")
    if counts:
        lines.append("\n## فرمول‌ها میان ویدیوهای برجسته\n")
        for f, n in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {f}: {n}")
    durs = [r["duration"] for r in hits if r["duration"]]
    rest = [r["duration"] for r in out if r["duration"] and r["multiple"] < 1]
    if durs and rest:
        lines.append(f"\n- میانهٔ مدت ویدیوهای برجسته {mmss(statistics.median(durs))}، "
                     f"ویدیوهای زیر میانه {mmss(statistics.median(rest))}")
    if thin:
        lines.append(f"\nکنار گذاشته شد (کمتر از ۴ ویدیو؛ میانهٔ یکی دو ویدیو میانه نیست): "
                     + "، ".join(f"{c} ({n})" for c, n in thin[:8]))
    lines.append(f"\n{len(rows)} ویدیو از {len(by)} کانال. با چند ده ردیف، این‌ها نشانه‌اند، نه قانون.\n")
    text = "\n".join(lines)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"نوشته شد: {a.out}\n")
    print(text)


if __name__ == "__main__":
    main()
