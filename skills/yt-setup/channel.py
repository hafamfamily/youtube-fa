#!/usr/bin/env python3
"""
channel.py - مدیریت کانال‌ها و پوشه‌های کاری بستهٔ youtube-fa.

بر پایهٔ page.py از instagram-fa؛ همان منطق، برای یوتیوب.

هر کانال یک پوشه دارد:
  <خانه>/<نام-کانال>/
      channel.md       شناسنامهٔ کانال (موضوع، مخاطب، لحن، برنامه، خطوط قرمز...)
      voice.md         صدای گفتاری سازنده: چطور جلوی دوربین حرف می‌زند (yt-script از آن می‌خواند)
      brand.json       رنگ‌ها، هندل، فونت و سبک تامبنیل
      plan/            برنامه‌های هفتگی (md و xlsx)
      videos/          هر ویدیو یک پوشه: status.json، script.md، package.md، thumb/، transcript.srt، ...
      data/            خروجی‌های یوتیوب استودیو (ریتنشن، آمار) برای yt-retention و yt-audit
      ready/           ویدیوهای تأییدشده و آمادهٔ آپلود
      publish.json     حالت تأیید و روش انتشار
      published.csv    دفتر انتشار
      swipe.md         فایل الهام از yt-viral
      insights.md      درس‌های yt-audit و yt-retention

«خانه» در Claude دسکتاپ خودکار پوشهٔ youtube-fa داخل پوشهٔ وصل‌شدهٔ لپ‌تاپ است (مثلاً
Documents/youtube-fa)؛ وگرنه ~/youtube-fa. با `channel.py home <مسیر>` عوضش کن.

استفاده:
  python channel.py where                   # کانال فعال و مسیرها (JSON)
  python channel.py list
  python channel.py new my-channel          # ساخت کانال تازه و فعال کردنش
  python channel.py use my-channel
  python channel.py home "D:/youtube"
  python channel.py item --type video --title "تست ۵ میکروفون ارزان" [--date 2026-10-24]
"""

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CONF = os.path.join(os.path.expanduser("~"), ".youtube-fa.json")
HOME_NAME = "youtube-fa"
MARKER = ".ytfa-home"
TYPES = ("video", "short", "live", "post")
SUBDIRS = ("plan", "videos", "data", "ready")


def setup_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def conf():
    if os.path.exists(CONF):
        try:
            with open(CONF, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_conf(c):
    with open(CONF, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)


def _detect_home():
    """Claude دسکتاپ پوشه‌های لپ‌تاپ را زیر ~/mnt/<نام پوشه> وصل می‌کند و ماشین هر جلسه از نو
    ساخته می‌شود؛ پس خانه را در پوشهٔ وصل‌شده پیدا می‌کنیم، نه در تنظیمات محلی."""
    hm = os.path.expanduser("~")
    mnt = os.path.join(hm, "mnt")
    if os.path.isdir(mnt):
        cands = []
        for d1 in sorted(os.listdir(mnt)):
            p1 = os.path.join(mnt, d1)
            if not os.path.isdir(p1):
                continue
            if d1 == HOME_NAME or os.path.exists(os.path.join(p1, MARKER)):
                cands.append(p1)
            cands.append(os.path.join(p1, HOME_NAME))
        for c in cands:
            if os.path.isdir(c):
                return c
        for d1 in ("Documents", "documents"):
            if os.path.isdir(os.path.join(mnt, d1)):
                return os.path.join(mnt, d1, HOME_NAME)
    return os.path.join(hm, HOME_NAME)


def home():
    return os.environ.get("YTFA_HOME") or conf().get("home") or _detect_home()


def active():
    """کانال فعال در خود خانه ذخیره می‌شود (فایل .active) تا بین جلسه‌ها بماند."""
    f = os.path.join(home(), ".active")
    if os.path.exists(f):
        with open(f, encoding="utf-8") as fh:
            v = fh.read().strip()
            if v:
                return v
    a = conf().get("active")
    if a:
        return a
    h = home()
    if os.path.isdir(h):
        chans = [d for d in os.listdir(h) if os.path.exists(os.path.join(h, d, "channel.md"))]
        if len(chans) == 1:
            return chans[0]
    return None


def set_active(slug):
    os.makedirs(home(), exist_ok=True)
    with open(os.path.join(home(), ".active"), "w", encoding="utf-8") as f:
        f.write(slug)
    try:
        c = conf()
        c["active"] = slug
        save_conf(c)
    except Exception:
        pass


def channel_dir(slug=None):
    slug = slug or active()
    return os.path.join(home(), slug) if slug else None


def slugify(text):
    s = re.sub(r"[^\w\u0600-\u06FF\-]+", "-", text.strip().lower()).strip("-")
    return s[:40] or "item"


def cmd_where(_):
    p = channel_dir()
    j = lambda *x: p and os.path.join(p, *x)  # noqa: E731
    print(json.dumps({
        "home": home(), "active": active(), "channel_dir": p,
        "exists": bool(p and os.path.isdir(p)),
        "channel_md": j("channel.md"), "voice_md": j("voice.md"), "brand_json": j("brand.json"),
        "videos": j("videos"), "plan": j("plan"), "data": j("data"), "ready": j("ready"),
        "swipe_md": j("swipe.md"), "insights_md": j("insights.md"),
        "skills_dir": os.path.dirname(HERE),
        "fonts": os.path.join(home(), "fonts"),
        "tools": os.path.join(home(), ".tools"),
    }, ensure_ascii=False, indent=2))


def cmd_list(_):
    h = home()
    chans = sorted(d for d in os.listdir(h) if os.path.exists(os.path.join(h, d, "channel.md"))) \
        if os.path.isdir(h) else []
    if not chans:
        print("هنوز هیچ کانالی ساخته نشده. اول: channel.py new <نام>")
        return
    for d in chans:
        print(("* " if d == active() else "  ") + d)


def cmd_new(a):
    slug = slugify(a.slug)
    p = channel_dir(slug)
    if os.path.exists(os.path.join(p, "channel.md")) and not a.force:
        print(f"این کانال از قبل هست: {p}  (برای فعال کردن: channel.py use {slug})")
        sys.exit(1)
    for sub in SUBDIRS:
        os.makedirs(os.path.join(p, sub), exist_ok=True)
    tpl = os.path.join(HERE, "templates")
    for name in ("channel.md", "voice.md", "brand.json"):
        dst = os.path.join(p, name)
        if a.force or not os.path.exists(dst):
            shutil.copy(os.path.join(tpl, name), dst)
    pub = os.path.join(p, "publish.json")
    if not os.path.exists(pub):
        with open(pub, "w", encoding="utf-8") as f:
            json.dump({"mode": "manual", "targets": ["youtube", "aparat"],
                       "method": {"youtube": "manual", "aparat": "manual"}, "privacy": "public",
                       "youtube_schedule": True, "notify_subscribers": True, "made_for_kids": False,
                       "ai_disclosure": True, "category_youtube": "27", "category_aparat": 0},
                      f, ensure_ascii=False, indent=2)
    log = os.path.join(p, "published.csv")
    if not os.path.exists(log):
        with open(log, "w", encoding="utf-8-sig") as f:
            f.write("تاریخ انتشار,کجا,نوع,عنوان,پوشه,لینک\n")
    marker = os.path.join(home(), MARKER)
    if not os.path.exists(marker):
        open(marker, "w").close()
    set_active(slug)
    print(json.dumps({"created": p, "active": slug}, ensure_ascii=False))


def cmd_use(a):
    slug = slugify(a.slug)
    if not os.path.exists(os.path.join(channel_dir(slug), "channel.md")):
        print(f"کانال «{slug}» پیدا نشد. فهرست: channel.py list")
        sys.exit(1)
    set_active(slug)
    print(f"کانال فعال: {slug}")


def cmd_home(a):
    path = os.path.abspath(os.path.expanduser(a.path))
    os.makedirs(path, exist_ok=True)
    c = conf()
    c["home"] = path
    save_conf(c)
    print(f"خانهٔ کانال‌ها: {path}")


def cmd_item(a):
    p = channel_dir()
    if not p or not os.path.isdir(p):
        print("کانال فعالی نیست. اول yt-setup را اجرا کن.")
        sys.exit(1)
    date = a.date or dt.date.today().isoformat()
    name = f"{date}-{a.type}-{slugify(a.title)}"
    d = os.path.join(p, "videos", name)
    n = 2
    while os.path.exists(d):
        d = os.path.join(p, "videos", f"{name}-{n}")
        n += 1
    os.makedirs(os.path.join(d, "thumb"))
    status = {"status": "idea", "type": a.type, "title": a.title, "date": date,
              "time": a.time or "", "created": dt.datetime.now().isoformat(timespec="minutes"),
              "history": []}
    with open(os.path.join(d, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    print(d)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="مدیریت کانال‌های youtube-fa")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("where").set_defaults(fn=cmd_where)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    n = sub.add_parser("new")
    n.add_argument("slug")
    n.add_argument("--force", action="store_true")
    n.set_defaults(fn=cmd_new)
    u = sub.add_parser("use")
    u.add_argument("slug")
    u.set_defaults(fn=cmd_use)
    h = sub.add_parser("home")
    h.add_argument("path")
    h.set_defaults(fn=cmd_home)
    i = sub.add_parser("item")
    i.add_argument("--type", choices=TYPES, required=True)
    i.add_argument("--title", required=True)
    i.add_argument("--date")
    i.add_argument("--time")
    i.set_defaults(fn=cmd_item)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
