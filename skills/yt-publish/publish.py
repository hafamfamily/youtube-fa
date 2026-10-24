#!/usr/bin/env python3
"""
publish.py - تأیید و انتشار ویدیو در یوتیوب و آپارات.

بر پایهٔ publish.py از instagram-fa؛ همان دو تنظیم، برای دو سکو.

حالت تأیید (mode):
  manual  هیچ ویدیویی بدون «بله»ی صاحب کانال آمادهٔ انتشار نمی‌شود (پیش‌فرض)
  auto    ویدیو بعد از چک‌های فنی، بدون سؤال تأیید می‌شود؛ اگر چکی رد شد، منتشر نمی‌شود و گزارش می‌گیرد
روش انتشار (method)، جدا برای هر سکو:
  manual  پوشهٔ ready/ با ویدیو، تامبنیل، عنوان، توضیحات، تگ و چک‌لیست؛ خودت آپلود می‌کنی
  api     آپلود خودکار (یوتیوب: YouTube Data API با yt_api.py؛ آپارات: aparat_api.py، تجربی)

در یوتیوب با «youtube_schedule»، ویدیوی تأییدشده زودتر آپلود می‌شود و خود یوتیوب سر ساعت منتشرش
می‌کند؛ پس لازم نیست کامپیوتر سر ساعت انتشار روشن باشد.

پوشهٔ هر ویدیو (videos/<ویدیو>/):
  status.json   وضعیت و تاریخچه (channel.py item می‌سازد)
  meta.json     {"title","description","tags":[],"category","privacy","made_for_kids","synthetic",
                 "targets":["youtube","aparat"], "thumb":"thumb/a.png",
                 "aparat": {"title","description","tags","category"}}   (بخش aparat اختیاری است)
  video.mp4     فایل نهایی (یا final.mp4 یا تنها mp4 پوشه)
  thumb/        تامبنیل‌ها (thumb.png یا همان که meta.thumb می‌گوید)

دستورها:
  python publish.py mode   --channel <کانال> [manual|auto]
  python publish.py method --channel <کانال> [--youtube manual|api] [--aparat manual|api] [--targets youtube,aparat]
  python publish.py check  <ویدیو>
  python publish.py approve <ویدیو> --approved-by "بله، منتشرش کن"     (متن دقیق جواب صاحب کانال)
  python publish.py approve <ویدیو> --auto                              (فقط در حالت auto)
  python publish.py publish <ویدیو> [--only youtube|aparat] [--dry-run]
  python publish.py due --channel <کانال> | --all [--dry-run]          (برای زمان‌بند)
  python publish.py schedule [--apply] [--remove] [--every 15]
  python publish.py revise <ویدیو> --note "..."
  python publish.py posted <ویدیو> --platform youtube|aparat [--url ...]   (ثبت آپلود دستی)
  python publish.py list --channel <کانال> [--status approved]

در هر دو حالت، ویدیویی که چک فنی‌اش FAIL دارد منتشر نمی‌شود.
"""

import argparse
import csv
import datetime as dt
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import settings  # noqa: E402

TYPE_FA = {"video": "ویدیو", "short": "شورتس", "live": "لایو", "post": "پست"}
STATUS_FA = {"idea": "ایده", "draft": "پیش‌نویس (منتظر تأیید)", "revise": "نیاز به اصلاح",
             "approved": "تأییدشده", "partial": "بخشی منتشر شده", "posted": "منتشرشده",
             "failed": "انتشار ناموفق", "scheduled": "زمان‌بندی‌شده", "pending": "در صف"}
P_FA = settings.PLATFORM_FA
SCHEDULE_LEAD_MIN = 20       # کمتر از این تا زمان انتشار، دیگر publishAt نمی‌گذاریم و مستقیم منتشر می‌کنیم


def setup_stdout():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


# ---------- فایل‌ها و وضعیت ----------

def load(d):
    p = os.path.join(d, "status.json")
    if not os.path.exists(p):
        print(f"status.json در {d} نیست؛ این پوشهٔ ویدیو نیست.", file=sys.stderr)
        sys.exit(2)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(d, st):
    tmp = os.path.join(d, "status.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(d, "status.json"))


def meta_of(d):
    p = os.path.join(d, "meta.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def now():
    return dt.datetime.now().isoformat(timespec="minutes")


def channel_of(item_dir):
    return os.path.dirname(os.path.dirname(os.path.abspath(item_dir)))


def log(channel, msg):
    print(msg)
    try:
        with open(os.path.join(channel, "publish.log"), "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}\n")
    except OSError:
        pass


def history(st, action, **kw):
    st.setdefault("history", []).append(dict({"at": now(), "action": action}, **kw))


def video_of(d):
    for n in ("video.mp4", "final.mp4", "video.mov", "final.mov"):
        if os.path.exists(os.path.join(d, n)):
            return os.path.join(d, n)
    vids = sorted(glob.glob(os.path.join(d, "*.mp4")) + glob.glob(os.path.join(d, "*.mov")))
    return vids[0] if len(vids) == 1 else None


def thumb_of(d, meta):
    if meta.get("thumb"):
        p = os.path.join(d, meta["thumb"])
        return p if os.path.exists(p) else None
    for n in ("thumb.png", "thumb.jpg"):
        for base in (os.path.join(d, "thumb"), d):
            if os.path.exists(os.path.join(base, n)):
                return os.path.join(base, n)
    imgs = sorted(glob.glob(os.path.join(d, "thumb", "*.png")) + glob.glob(os.path.join(d, "thumb", "*.jpg")))
    imgs = [i for i in imgs if os.path.basename(i) != "preview.png"]
    return imgs[0] if imgs else None


def targets_of(st, meta, cfg):
    return [t for t in (meta.get("targets") or cfg["targets"]) if t in P_FA]


def ffprobe_info(path):
    fp = shutil.which("ffprobe")
    if not fp:
        return {}
    r = subprocess.run([fp, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
    except ValueError:
        return {}
    info = {"duration": float(j.get("format", {}).get("duration", 0) or 0), "audio": False}
    for s in j.get("streams", []):
        if s.get("codec_type") == "video" and "width" not in info:
            info.update(vcodec=s.get("codec_name"), width=s.get("width"), height=s.get("height"))
        elif s.get("codec_type") == "audio":
            info["audio"] = True
    return info


def banned_words(channel):
    """کلمه‌های ممنوع از voice.md (بخش «کلمه‌هایی که هرگز نمی‌گویم»)."""
    p = os.path.join(channel, "voice.md")
    if not os.path.exists(p):
        return []
    out, inside = [], False
    with open(p, encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                inside = "هرگز نمی‌گویم" in line
                continue
            if inside and line.strip() and not line.strip().startswith(("مثلاً", ">")):
                for w in line.replace("،", ",").replace("؛", ",").split(","):
                    w = w.strip(" -*«»\"'.\n")
                    if len(w) >= 2:
                        out.append(w)
    return out


# ---------- چک فنی ----------

def preflight(d, st, cfg=None):
    """[(سطح, پیام)]؛ FAIL یعنی منتشر نشود."""
    channel = channel_of(d)
    cfg = cfg or settings.load(channel)
    meta = meta_of(d)
    out = []
    v = video_of(d)
    if not v:
        out.append(("FAIL", "فایل ویدیو نیست (video.mp4 در پوشهٔ ویدیو)."))
    else:
        info = ffprobe_info(v)
        dur = info.get("duration", 0)
        if info and dur < 1:
            out.append(("FAIL", "ffprobe مدت ویدیو را نخواند؛ فایل سالم است؟"))
        if st.get("type") == "short" and info:
            if dur > 180:
                out.append(("WARN", f"شورتس {dur:.0f} ثانیه است؛ بالای ۳ دقیقه شورتس حساب نمی‌شود."))
            if info.get("width") and info.get("height") and info["width"] > info["height"]:
                out.append(("WARN", "شورتس افقی است؛ برای شورتس عمودی یا مربعی بساز."))
        if info and dur > 15 * 60:
            out.append(("WARN", "ویدیو بالای ۱۵ دقیقه است؛ کانال یوتیوب باید تأیید شماره تلفن داشته باشد."))
        if info and not info.get("audio"):
            out.append(("WARN", "ویدیو صدا ندارد."))
    if not meta:
        out.append(("FAIL", "meta.json نیست (عنوان، توضیحات، تگ‌ها)؛ با yt-package و yt-seo بساز."))
    title = (meta.get("title") or "").strip()
    desc = meta.get("description") or ""
    if meta and not title:
        out.append(("FAIL", "عنوان خالی است."))
    if len(title) > 100:
        out.append(("FAIL", f"عنوان {len(title)} حرف است؛ سقف یوتیوب ۱۰۰."))
    for name, txt in (("عنوان", title), ("توضیحات", desc)):
        if "<" in txt or ">" in txt:
            out.append(("FAIL", f"{name} علامت < یا > دارد؛ یوتیوب قبول نمی‌کند."))
    if len(desc.encode("utf-8")) > 5000:
        out.append(("FAIL", f"توضیحات {len(desc.encode('utf-8'))} بایت است؛ سقف یوتیوب ۵۰۰۰ بایت (هر حرف فارسی ۲ بایت)."))
    tags = meta.get("tags") or []
    tlen = sum(len(t) for t in tags) + max(0, len(tags) - 1)
    if tlen > 500:
        out.append(("FAIL", f"تگ‌ها {tlen} حرف‌اند؛ سقف ۵۰۰."))
    th = thumb_of(d, meta)
    if st.get("type") != "short":
        if not th:
            out.append(("WARN", "تامبنیل نیست (thumb/thumb.png)؛ یوتیوب یک فریم تصادفی می‌گذارد."))
        else:
            try:
                from PIL import Image
                w, h = Image.open(th).size
                if abs(w / h - 16 / 9) > 0.03:
                    out.append(("WARN", f"تامبنیل {w}×{h} است؛ ۱۶:۹ (۱۲۸۰×۷۲۰) نیست."))
                if w < 640:
                    out.append(("FAIL", f"عرض تامبنیل {w} است؛ یوتیوب حداقل ۶۴۰ می‌خواهد."))
            except Exception:
                pass
            if os.path.getsize(th) > 2 * 1024 * 1024:
                out.append(("WARN", "تامبنیل بیش از ۲ مگابایت است؛ هنگام آپلود به JPEG فشرده می‌شود."))
    bad = [w for w in banned_words(channel) if w and (w in title or w in desc)]
    if bad:
        out.append(("FAIL", f"کلمه‌های ممنوع کانال: {'، '.join(bad)}"))
    tg = targets_of(st, meta, cfg)
    if not tg:
        out.append(("FAIL", "هیچ سکویی برای انتشار انتخاب نشده (targets)."))
    if "aparat" in tg and cfg["method"].get("aparat") == "api":
        cat = (meta.get("aparat") or {}).get("category") or cfg.get("category_aparat")
        if not cat:
            out.append(("FAIL", "دستهٔ آپارات تعیین نشده (category_aparat در publish.json یا meta.aparat.category)."))
    for p in tg:
        if cfg["method"].get(p) == "api" and p not in settings.secrets(channel):
            out.append(("WARN", f"روش انتشار {P_FA[p]} خودکار است ولی هنوز وصل نشده؛ تا وصل نشود منتشر نمی‌شود."))
    return out


def print_checks(res):
    if not res:
        print("  PASS  همهٔ چک‌ها")
    for lvl, msg in res:
        print(f"  {lvl:<4}  {msg}")


def fails(res):
    return [m for lvl, m in res if lvl == "FAIL"]


# ---------- آماده‌سازی برای آپلود دستی ----------

def checklist(st, meta, targets, files):
    L = [f"# انتشار: {meta.get('title') or st.get('title')}", "",
         f"نوع: {TYPE_FA.get(st.get('type'), st.get('type'))}  ·  زمان پیشنهادی: {st.get('date', '')} {st.get('time', '')}", ""]
    if "youtube" in targets:
        L += ["## یوتیوب (studio.youtube.com ← Create ← Upload videos)", "",
              "1. `video.mp4` را بکش و رها کن.",
              "2. عنوان را از `عنوان.txt` و توضیحات را از `توضیحات.txt` کپی کن.",
              "3. Thumbnail ← `thumb` این پوشه." if any(f.startswith("thumb") for f in files) else
              "3. تامبنیل: فریمی را انتخاب کن که موضوع در آن پیداست.",
              "4. Audience: «No, it's not made for kids» (مگر واقعاً برای کودک باشد).",
              "5. Show more ← Tags: از `تگ‌ها.txt`؛ Language: Persian.",
              "6. اگر ویدیو تصویر یا صدای ساختگیِ واقع‌نما دارد، گزینهٔ Altered content را «Yes» بزن.",
              "7. Visibility ← Schedule ← همان زمان پیشنهادی (به وقت مخاطب).", ""]
    if "aparat" in targets:
        L += ["## آپارات (aparat.com ← بارگذاری ویدیو)", "",
              "1. `video.mp4` را انتخاب کن.",
              "2. عنوان، توضیحات و برچسب‌ها را از فایل‌های `آپارات-*.txt` کپی کن (اگر نبود، از همان فایل‌های یوتیوب).",
              "3. دسته‌بندی را انتخاب کن و تصویر شاخص را از `thumb` بگذار.", ""]
    L += ["## بعد از انتشار", "",
          "- به Claude بگو «منتشر کردم» (با لینک) تا در دفتر انتشار ثبت شود.",
          "- ساعت اول به کامنت‌ها جواب بده (yt-comment کمکت می‌کند).", ""]
    return "\n".join(L)


def make_ready(d, st, cfg):
    meta = meta_of(d)
    channel = channel_of(d)
    out = os.path.join(channel, "ready", os.path.basename(d))
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    files = []
    v = video_of(d)
    if v:
        shutil.copy(v, os.path.join(out, "video" + os.path.splitext(v)[1]))
        files.append("video" + os.path.splitext(v)[1])
    th = thumb_of(d, meta)
    if th:
        shutil.copy(th, os.path.join(out, "thumb" + os.path.splitext(th)[1]))
        files.append("thumb" + os.path.splitext(th)[1])

    def w(name, text):
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
        files.append(name)

    w("عنوان.txt", meta.get("title", ""))
    w("توضیحات.txt", meta.get("description", ""))
    w("تگ‌ها.txt", ", ".join(meta.get("tags") or []))
    ap = meta.get("aparat") or {}
    if ap:
        w("آپارات-عنوان.txt", ap.get("title") or meta.get("title", ""))
        w("آپارات-توضیحات.txt", ap.get("description") or meta.get("description", ""))
        w("آپارات-برچسب‌ها.txt", "، ".join(ap.get("tags") or meta.get("tags") or []))
    w("انتشار.md", checklist(st, meta, targets_of(st, meta, cfg), files))
    return out, files


# ---------- تأیید ----------

def approve(d, st, by, auto=False):
    cfg = settings.load(channel_of(d))
    res = preflight(d, st, cfg)
    if fails(res):
        return False, res
    out, _ = make_ready(d, st, cfg)
    st["status"] = "approved"
    st["ready_dir"] = out
    st.pop("error", None)
    meta = meta_of(d)
    plats = st.setdefault("platforms", {})
    for p in targets_of(st, meta, cfg):
        if plats.get(p, {}).get("status") not in ("posted", "scheduled"):
            plats[p] = {"status": "pending"}
    history(st, "approved", by=by, auto=auto)
    save(d, st)
    return True, res


def cmd_approve(a):
    d = os.path.abspath(a.item)
    st = load(d)
    cfg = settings.load(channel_of(d))
    if st["status"] == "posted":
        print("این ویدیو قبلاً منتشر شده.", file=sys.stderr)
        sys.exit(1)
    if a.auto:
        if cfg["mode"] != "auto":
            print("حالت این کانال «دستی» است؛ تأیید خودکار مجاز نیست. یا --approved-by با جواب صاحب کانال، "
                  "یا: publish.py mode --channel <کانال> auto", file=sys.stderr)
            sys.exit(2)
        by = "خودکار (حالت auto)"
    else:
        if not a.approved_by or len(a.approved_by.strip()) < 2:
            print("بدون متن تأیید صاحب کانال نمی‌شود تأیید کرد (--approved-by).", file=sys.stderr)
            sys.exit(2)
        by = a.approved_by.strip()
    ok, res = approve(d, st, by, auto=a.auto)
    print_checks(res)
    if not ok:
        print("\nتأیید نشد؛ اول ایرادهای FAIL را درست کن.", file=sys.stderr)
        sys.exit(1)
    st = load(d)
    print(json.dumps({"status": "approved", "ready_dir": st["ready_dir"],
                      "method": {p: cfg["method"].get(p) for p in st.get("platforms", {})},
                      "when": f"{st.get('date', '')} {st.get('time', '')}".strip()}, ensure_ascii=False, indent=2))


# ---------- انتشار ----------

def due_time(st):
    try:
        day = dt.date.fromisoformat(st.get("date", ""))
    except ValueError:
        return dt.datetime.min
    hh, mm = 0, 0
    if st.get("time"):
        try:
            hh, mm = (int(x) for x in st["time"].split(":")[:2])
        except ValueError:
            pass
    return dt.datetime.combine(day, dt.time(hh, mm))


def to_utc_iso(local_dt):
    return local_dt.astimezone().astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def thumb_for_upload(path, work):
    """یوتیوب تامبنیل تا ۲ مگابایت می‌گیرد؛ اگر بزرگ‌تر بود به JPEG فشرده می‌شود."""
    if os.path.getsize(path) <= 2 * 1024 * 1024:
        return path
    from PIL import Image
    im = Image.open(path).convert("RGB")
    out = os.path.join(work, "thumb.jpg")
    for q in (90, 82, 74, 66):
        im.save(out, "JPEG", quality=q, optimize=True)
        if os.path.getsize(out) <= 2 * 1024 * 1024:
            break
    return out


def record_posted(d, st, platform_, url="", vid="", how="manual", scheduled_for=None):
    plats = st.setdefault("platforms", {})
    plats[platform_] = {"status": "scheduled" if scheduled_for else "posted", "url": url, "id": vid,
                        "at": now(), **({"publish_at": scheduled_for} if scheduled_for else {})}
    history(st, "scheduled" if scheduled_for else "posted", platform=platform_, url=url, how=how)
    done = all(p.get("status") in ("posted", "scheduled") for p in plats.values())
    st["status"] = "posted" if done else "partial"
    if done:
        st["posted_at"] = now()
        st.pop("error", None)
    save(d, st)
    path = os.path.join(channel_of(d), "published.csv")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["تاریخ انتشار", "کجا", "نوع", "عنوان", "پوشه", "لینک"])
        when = scheduled_for or now()
        w.writerow([when, P_FA.get(platform_, platform_), TYPE_FA.get(st.get("type"), st.get("type")),
                    meta_of(d).get("title") or st.get("title"), os.path.basename(d), url])


def fail(d, st, platform_, err):
    st.setdefault("platforms", {})[platform_] = dict(st.get("platforms", {}).get(platform_, {}),
                                                     status="failed", error=str(err))
    st["status"] = "failed"
    st["error"] = f"{P_FA[platform_]}: {err}"
    history(st, "failed", platform=platform_, error=str(err))
    save(d, st)


def publish_youtube(d, st, cfg, at, dry):
    import yt_api
    channel = channel_of(d)
    meta = meta_of(d)
    due = due_time(st)
    sched = None
    if cfg.get("youtube_schedule") and due > at + dt.timedelta(minutes=SCHEDULE_LEAD_MIN):
        sched = to_utc_iso(due)
    privacy = meta.get("privacy") or cfg.get("privacy", "public")
    body = {
        "snippet": {"title": meta["title"].strip(), "description": meta.get("description", ""),
                    "tags": meta.get("tags") or [], "categoryId": str(meta.get("category") or cfg["category_youtube"]),
                    "defaultLanguage": meta.get("language", "fa"), "defaultAudioLanguage": meta.get("language", "fa")},
        "status": {"privacyStatus": "private" if sched else privacy,
                   "selfDeclaredMadeForKids": bool(meta.get("made_for_kids", cfg.get("made_for_kids", False))),
                   "embeddable": True},
        "_notify": bool(cfg.get("notify_subscribers", True)),
    }
    if sched:
        body["status"]["publishAt"] = sched
    if cfg.get("ai_disclosure") and meta.get("synthetic"):
        body["status"]["containsSyntheticMedia"] = True
    title = f"«{meta['title']}»"
    if dry:
        log(channel, f"   یوتیوب (آزمایشی): {json.dumps({k: v for k, v in body.items() if k != '_notify'}, ensure_ascii=False)[:400]}")
        return True
    log(channel, f"→ آپلود یوتیوب {title}" + (f" (انتشار خودکار در {st.get('date')} {st.get('time')})" if sched else ""))
    res = yt_api.upload_video(channel, video_of(d), body, log=lambda m: log(channel, m))
    vid = res["id"]
    url = f"https://youtu.be/{vid}"
    th = thumb_of(d, meta)
    if th and st.get("type") != "short":
        work = os.path.join(d, ".upload")
        os.makedirs(work, exist_ok=True)
        try:
            yt_api.set_thumbnail(channel, vid, thumb_for_upload(th, work))
        except yt_api.ApiError as e:
            log(channel, f"   ⚠ تامبنیل گذاشته نشد ({e}). تامبنیل سفارشی نیاز به تأیید شماره تلفن کانال دارد؛ "
                         "در استودیو دستی بگذار.")
        shutil.rmtree(work, ignore_errors=True)
    try:
        s = yt_api.video_status(channel, vid).get("status", {})
        want = "private" if sched else privacy
        if s.get("privacyStatus") and s["privacyStatus"] != want:
            log(channel, f"   ⚠ یوتیوب وضعیت ویدیو را «{s['privacyStatus']}» گذاشت، نه «{want}». در استودیو بررسی کن.")
    except Exception:
        pass
    record_posted(d, st, "youtube", url, vid, "api", scheduled_for=(f"{st.get('date')} {st.get('time')}" if sched else None))
    log(channel, f"✓ یوتیوب: {url}" + (" (زمان‌بندی‌شده)" if sched else ""))
    return True


def publish_aparat(d, st, cfg, dry):
    import aparat_api
    channel = channel_of(d)
    meta = meta_of(d)
    ap = meta.get("aparat") or {}
    title = (ap.get("title") or meta["title"]).strip()
    cat = ap.get("category") or cfg.get("category_aparat")
    tags = ap.get("tags") or meta.get("tags") or []
    descr = ap.get("description") or meta.get("description", "")
    if dry:
        log(channel, f"   آپارات (آزمایشی): {title} · دسته {cat} · {len(tags)} برچسب")
        return True
    log(channel, f"→ آپلود آپارات «{title}»")
    r = aparat_api.upload(channel, video_of(d), title, cat, tags, descr, log=lambda m: log(channel, m))
    record_posted(d, st, "aparat", r["url"], r["uid"], "api")
    log(channel, f"✓ آپارات: {r['url']}  (پردازش آپارات ممکن است چند دقیقه طول بکشد)")
    return True


def publish_item(d, dry=False, only=None, at=None, force_now=False):
    """هر سکوی «pending» این ویدیو را که وقتش رسیده منتشر می‌کند. خروجی: تعداد انتشار."""
    st = load(d)
    channel = channel_of(d)
    cfg = settings.load(channel)
    meta = meta_of(d)
    at = at or dt.datetime.now()
    if st["status"] not in ("approved", "partial", "failed"):
        log(channel, f"✗ «{st.get('title')}»: وضعیت «{STATUS_FA.get(st['status'], st['status'])}» است؛ فقط تأییدشده منتشر می‌شود.")
        return 0
    res = preflight(d, st, cfg)
    if fails(res):
        st["status"] = "failed"
        st["error"] = "؛ ".join(fails(res))
        history(st, "failed", error=st["error"])
        save(d, st)
        log(channel, f"✗ «{st.get('title')}»: چک فنی رد شد: {st['error']}")
        return 0
    n = 0
    due = due_time(st)
    for p in targets_of(st, meta, cfg):
        if only and p != only:
            continue
        ps = st.get("platforms", {}).get(p, {}).get("status")
        if ps in ("posted", "scheduled"):
            continue
        if cfg["method"].get(p) != "api" and not dry:
            cur = load(d)
            if not cur.get("platforms", {}).get(p, {}).get("notified"):   # فقط یک بار، نه در هر اجرای زمان‌بند
                log(channel, f"• {P_FA[p]}: روش انتشار دستی است؛ فایل‌ها در ready/ آماده‌اند.")
                cur.setdefault("platforms", {}).setdefault(p, {"status": "pending"})["notified"] = True
                save(d, cur)
            continue
        early_ok = p == "youtube" and cfg.get("youtube_schedule")
        if due > at and not early_ok and not force_now:
            continue
        try:
            ok = publish_youtube(d, load(d), cfg, at, dry) if p == "youtube" else publish_aparat(d, load(d), cfg, dry)
            n += int(bool(ok))
        except Exception as e:  # خطای یک سکو نباید سکوی دیگر را متوقف کند
            transient = getattr(e, "transient", False)
            if transient:
                log(channel, f"   ⚠ {P_FA[p]}: خطای موقت ({e})؛ در اجرای بعدی دوباره امتحان می‌شود.")
            else:
                fail(d, load(d), p, e)
                log(channel, f"✗ {P_FA[p]}: {e}")
    return n


def cmd_publish(a):
    d = os.path.abspath(a.item)
    with Lock(channel_of(d)):
        n = publish_item(d, dry=a.dry_run, only=a.only, force_now=True)
    if not n and not a.dry_run:
        sys.exit(1)


class Lock:
    """جلوی دو اجرای هم‌زمان روی یک کانال را می‌گیرد (مثلاً زمان‌بند و دستی)."""

    def __init__(self, channel):
        self.p = os.path.join(channel, ".publish.lock")

    def __enter__(self):
        if os.path.exists(self.p) and time.time() - os.path.getmtime(self.p) < 3 * 3600:
            print("یک انتشار دیگر روی این کانال در حال اجراست.", file=sys.stderr)
            sys.exit(3)
        with open(self.p, "w") as f:
            f.write(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        try:
            os.remove(self.p)
        except OSError:
            pass


def run_due(channel, dry=False, at=None):
    cfg = settings.load(channel)
    at = at or dt.datetime.now()
    n = 0
    for sp in sorted(glob.glob(os.path.join(channel, "videos", "*", "status.json"))):
        d = os.path.dirname(sp)
        st = load(d)
        early = cfg.get("youtube_schedule") and cfg["method"].get("youtube") == "api"
        if due_time(st) > at and not early:
            continue
        if st["status"] == "draft" and cfg["mode"] == "auto" and due_time(st) <= at + dt.timedelta(days=7):
            ok, res = approve(d, st, "خودکار (حالت auto)", auto=True)
            if not ok:
                st = load(d)
                st["status"] = "failed"
                st["error"] = "؛ ".join(fails(res))
                history(st, "failed", error=st["error"])
                save(d, st)
                log(channel, f"✗ «{st.get('title')}»: تأیید خودکار نشد: {st['error']}")
                continue
            st = load(d)
        if st["status"] in ("approved", "partial"):
            n += publish_item(d, dry=dry, at=at)
    return n


def channels_home():
    sys.path.insert(0, os.path.join(SKILLS, "yt-setup"))
    import channel as C
    return C.home()


def cmd_due(a):
    if a.all:
        h = channels_home()
        chans = [os.path.join(h, x) for x in sorted(os.listdir(h))
                 if os.path.exists(os.path.join(h, x, "channel.md"))] if os.path.isdir(h) else []
    elif a.channel:
        chans = [os.path.abspath(a.channel)]
    else:
        print("--channel یا --all لازم است.", file=sys.stderr)
        sys.exit(2)
    total = 0
    for c in chans:
        with Lock(c):
            total += run_due(c, dry=a.dry_run)
    if not total:
        print("چیزی برای انتشار در این لحظه نبود.")


def cmd_schedule(a):
    """اجرای «due --all» هر چند دقیقه روی همین کامپیوتر."""
    py = sys.executable
    me = os.path.abspath(__file__)
    name = "youtube-fa"
    if platform.system() == "Windows":
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        runner = pyw if os.path.exists(pyw) else py
        cmd = (["schtasks", "/Delete", "/F", "/TN", name] if a.remove else
               ["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(a.every), "/TN", name,
                "/TR", f'"{runner}" "{me}" due --all'])
        shown = " ".join(cmd)
    else:
        line = f'*/{a.every} * * * * "{py}" "{me}" due --all >/dev/null 2>&1  # {name}'
        cmd = (["sh", "-c", f"crontab -l 2>/dev/null | grep -v '# {name}$' | crontab -"] if a.remove else
               ["sh", "-c", f"(crontab -l 2>/dev/null | grep -v '# {name}$'; echo '{line}') | crontab -"])
        shown = line if not a.remove else "حذف خط youtube-fa از crontab"
    if not a.apply:
        print("این دستور زمان‌بند را تنظیم می‌کند (برای اجرا --apply بزن):\n\n  " + shown)
        return
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("تنظیم زمان‌بند نشد:\n" + (r.stderr or r.stdout), file=sys.stderr)
        sys.exit(1)
    print("زمان‌بند حذف شد." if a.remove else
          f"زمان‌بند تنظیم شد: هر {a.every} دقیقه ویدیوهای رسیده منتشر می‌شوند. گزارش: <پوشهٔ کانال>/publish.log")


def cmd_mode(a):
    ch = os.path.abspath(a.channel)
    cfg = settings.load(ch)
    if a.value:
        cfg["mode"] = a.value
        settings.save(ch, cfg)
    show_cfg(ch, cfg)


def cmd_method(a):
    ch = os.path.abspath(a.channel)
    cfg = settings.load(ch)
    if a.youtube:
        cfg["method"]["youtube"] = a.youtube
    if a.aparat:
        cfg["method"]["aparat"] = a.aparat
    if a.targets:
        cfg["targets"] = [t.strip() for t in a.targets.split(",") if t.strip() in P_FA]
    settings.save(ch, cfg)
    show_cfg(ch, cfg)


def show_cfg(ch, cfg):
    sec = settings.secrets(ch)
    print(f"حالت تأیید: {settings.MODES[cfg['mode']]}")
    for p in cfg["targets"]:
        m = cfg["method"].get(p, "manual")
        conn = "" if m != "api" else ("  (وصل است)" if p in sec else "  (هنوز وصل نشده)")
        print(f"{P_FA[p]}: {settings.METHODS[m]}{conn}")
    if "youtube" in cfg["targets"] and cfg["method"].get("youtube") == "api":
        print("زمان‌بندی یوتیوب: " + ("زودتر آپلود، خود یوتیوب سر ساعت منتشر می‌کند" if cfg.get("youtube_schedule")
                                     else "آپلود سر ساعت"))


def cmd_check(a):
    d = os.path.abspath(a.item)
    res = preflight(d, load(d))
    print_checks(res)
    sys.exit(1 if fails(res) else 0)


def cmd_revise(a):
    d = os.path.abspath(a.item)
    st = load(d)
    st["status"] = "revise"
    history(st, "revise", note=a.note or "")
    save(d, st)
    print(f"برگشت برای اصلاح: {st.get('title')}")


def cmd_posted(a):
    d = os.path.abspath(a.item)
    st = load(d)
    if st["status"] not in ("approved", "partial", "failed"):
        print("فقط ویدیوی تأییدشده را می‌شود «منتشرشده» ثبت کرد.", file=sys.stderr)
        sys.exit(1)
    record_posted(d, st, a.platform, a.url or "")
    print(f"ثبت شد: {P_FA[a.platform]} · {st.get('title')}")


def cmd_list(a):
    rows = []
    for sp in sorted(glob.glob(os.path.join(os.path.abspath(a.channel), "videos", "*", "status.json"))):
        with open(sp, encoding="utf-8") as f:
            st = json.load(f)
        if a.status and st["status"] != a.status:
            continue
        plats = " ".join(f"{P_FA.get(p, p)}:{STATUS_FA.get(v.get('status'), v.get('status'))}"
                         for p, v in st.get("platforms", {}).items())
        extra = f"  ← {st['error']}" if st.get("status") == "failed" and st.get("error") else ""
        rows.append(f"{st.get('date', '')} {st.get('time', ''):<5}  {STATUS_FA.get(st['status'], st['status']):<22} "
                    f"{TYPE_FA.get(st.get('type'), st.get('type')):<6} {st.get('title')}{extra}\n"
                    f"            {plats}  {os.path.dirname(sp)}")
    print("\n".join(rows) if rows else "ویدیویی نیست.")


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="تأیید و انتشار یوتیوب و آپارات")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("mode")
    p.add_argument("value", nargs="?", choices=list(settings.MODES))
    p.add_argument("--channel", required=True)
    p.set_defaults(fn=cmd_mode)
    p = sub.add_parser("method")
    p.add_argument("--channel", required=True)
    p.add_argument("--youtube", choices=list(settings.METHODS))
    p.add_argument("--aparat", choices=list(settings.METHODS))
    p.add_argument("--targets", help="youtube,aparat")
    p.set_defaults(fn=cmd_method)
    p = sub.add_parser("check")
    p.add_argument("item")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("approve")
    p.add_argument("item")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--approved-by")
    g.add_argument("--auto", action="store_true")
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("publish")
    p.add_argument("item")
    p.add_argument("--only", choices=list(P_FA))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_publish)
    p = sub.add_parser("due")
    p.add_argument("--channel")
    p.add_argument("--all", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_due)
    p = sub.add_parser("schedule")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--remove", action="store_true")
    p.add_argument("--every", type=int, default=15)
    p.set_defaults(fn=cmd_schedule)
    p = sub.add_parser("revise")
    p.add_argument("item")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_revise)
    p = sub.add_parser("posted")
    p.add_argument("item")
    p.add_argument("--platform", choices=list(P_FA), required=True)
    p.add_argument("--url")
    p.set_defaults(fn=cmd_posted)
    p = sub.add_parser("list")
    p.add_argument("--channel", required=True)
    p.add_argument("--status", choices=list(STATUS_FA))
    p.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
