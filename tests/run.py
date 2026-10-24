#!/usr/bin/env python3
"""
run.py - تست سرتاسری youtube-fa پیش از هر نسخه.

  python tests/run.py            # همهٔ تست‌ها (اکسل و تامبنیل اگر کتابخانه‌شان نصب است)

هیچ چیزی به اینترنت فرستاده نمی‌شود: انتشار یوتیوب و آپارات با یک سرور ساختگی محلی (mock_api.py) آزموده
می‌شود. خانهٔ کانال‌ها در یک پوشهٔ موقت ساخته و آخر کار پاک می‌شود.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

T = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(T)
SK = os.path.join(ROOT, "skills")
PY = sys.executable
TMP = tempfile.mkdtemp(prefix="ytfa-test-")
ENV = dict(os.environ, YTFA_HOME=os.path.join(TMP, "home"), PYTHONIOENCODING="utf-8")
results = []


def run(args, ok_codes=(0,), env=None):
    r = subprocess.run([PY, "-I"] + args, capture_output=True, text=True, encoding="utf-8", env=env or ENV)
    if r.returncode not in ok_codes:
        raise AssertionError(f"exit {r.returncode}: {' '.join(args)}\n{r.stdout[-800:]}\n{r.stderr[-800:]}")
    return r.stdout


def test(name):
    def deco(fn):
        try:
            fn()
            results.append((name, "PASS", ""))
        except Exception as e:
            results.append((name, "FAIL", str(e)[:600]))
        return fn
    return deco


def S(*p):
    return os.path.join(SK, *p)


@test("fa_text کپی‌ها یکسان‌اند")
def _():
    run([os.path.join(ROOT, "tools", "sync_fa_text.py"), "--check"])


@test("کامپایل همهٔ اسکریپت‌ها")
def _():
    for d, _, fs in os.walk(ROOT):
        for f in fs:
            if f.endswith(".py"):
                subprocess.run([PY, "-m", "py_compile", os.path.join(d, f)], check=True)


@test("hookscore: قلاب بد رد و خوب بالا")
def _():
    out = json.loads(run([S("yt-script", "hookscore.py"), os.path.join(T, "hooks.txt"), "--json"]))
    by = {r["hook"]: r for r in out}
    bad = [h for h in by if h.startswith("سلام")][0]
    assert by[bad]["score"] < 20 and by[bad]["flags"], "قلاب سلام‌دار باید ردّی بخورد"
    assert out[0]["score"] >= 55, f"بهترین قلاب زیر ۵۵: {out[0]}"
    assert all(r["formula"] for r in out if "چرا" in r["hook"]), "سؤال باید فرمول بخورد"


@test("hooks.json: ۲۱ فرمول و regex معتبر")
def _():
    import re
    d = json.load(open(S("yt-script", "hooks.json"), encoding="utf-8"))
    assert len(d["hooks"]) == 21
    for h in d["hooks"]:
        for p in h["match"]:
            re.compile(p)
        assert h["example"] and h["fails_when"]


@test("title.py: تکرار و کلیک‌بیت")
def _():
    r = json.loads(run([S("yt-package", "title.py"), "--title", "باورتون نمیشه!!! بهترین میکروفون",
                        "--thumb", "بهترین میکروفون", "--json"]))
    kinds = {k for k, _ in r["issues"]}
    assert {"تکرار", "کلیک‌بیت", "کلی‌گویی"} <= kinds, kinds
    g = json.loads(run([S("yt-package", "title.py"), "--title", "تست ۵ میکروفون زیر ۲ میلیون",
                        "--thumb", "برنده: ارزون‌ترین", "--json"]))
    assert g["score"] >= 90, g


@test("deadair: سکوت، پرکننده، تکرار")
def _():
    r = json.loads(run([S("yt-edit", "deadair.py"), os.path.join(T, "sample.srt"), "--json"]))
    kinds = "".join(c["kind"] for c in r["cuts"])
    assert "DEAD" in kinds and "FILLER" in kinds and "REPEAT" in kinds, kinds
    assert 0 < r["removed"] < r["duration"]


@test("chapters: معتبر از زیرنویس و رد فهرست نامعتبر")
def _():
    r = json.loads(run([S("yt-chapters", "chapters.py"), os.path.join(T, "sample.srt"), "--target", "5", "--json"]))
    assert r["valid"] and r["chapters"][0]["label"] == "0:00", r
    bad = os.path.join(TMP, "bad.txt")
    open(bad, "w", encoding="utf-8").write("0:00 مقدمه\n0:05 دوم\n")
    run([S("yt-chapters", "chapters.py"), "--check", bad], ok_codes=(1,))


@test("retention: نشت قلاب و پرتگاه با متن")
def _():
    r = json.loads(run([S("yt-retention", "retention.py"), os.path.join(T, "retention.csv"),
                        "--duration", "1:58", "--json"]))
    assert r["hook_leak"] > 25 and len(r["cliffs"]) >= 2, r


@test("swipe: میانهٔ کانال و کنار گذاشتن کانال کم‌داده")
def _():
    r = json.loads(run([S("yt-viral", "swipe.py"), os.path.join(T, "ch1.json"), os.path.join(T, "ch2.json"), "--json"]))
    assert r["outliers"][0]["multiple"] > 5 and r["skipped_thin_channels"], r


@test("shorts: پنجره‌های مستقل")
def _():
    r = json.loads(run([S("yt-shorts", "shorts.py"), os.path.join(T, "sample.srt"), "--json"]))
    assert r and all(20 <= c["length"] <= 58 for c in r), r


@test("seo: تگ تکراری و کوئری")
def _():
    r = json.loads(run([S("yt-seo", "seo.py"), "--title", "تست میکروفون", "--desc", os.path.join(T, "desc.txt"),
                        "--tags", "الف, ب, الف", "--queries", "میکروفون ارزان برای یوتیوب|دوربین عکاسی", "--json"]))
    msgs = " ".join(r["issues"])
    assert "تکراری" in msgs and "دوربین عکاسی" in msgs, r


@test("yt-human: کلیشهٔ یوتیوب حذف، نیم‌فاصله سالم")
def _():
    src = os.path.join(TMP, "d.txt")
    out = os.path.join(TMP, "c.txt")
    open(src, "w", encoding="utf-8").write("سلام به همه دوستان عزیز، به کانال ما خوش اومدید. می‌خوام یه چیز بگم.\n")
    run([S("yt-human", "humanize.py"), src, "--out", out])
    t = open(out, encoding="utf-8").read()
    assert "خوش اومدید" not in t and "می‌خوام" in t and "،." not in t, t


@test("channel.py: کانال، پوشهٔ ویدیو، جابه‌جایی")
def _():
    run([S("yt-setup", "channel.py"), "new", "test-a"])
    run([S("yt-setup", "channel.py"), "new", "test-b"])
    run([S("yt-setup", "channel.py"), "use", "test-a"])
    w = json.loads(run([S("yt-setup", "channel.py"), "where"]))
    assert w["active"] == "test-a" and os.path.exists(w["voice_md"])


try:
    import openpyxl  # noqa: F401
    HAVE_XL = True
except ImportError:
    HAVE_XL = False


@test("plan_xlsx: اکسل با تاریخ شمسی و برگهٔ وقت")
def _():
    if not HAVE_XL:
        raise AssertionError("openpyxl نصب نیست (pip install openpyxl)")
    out = os.path.join(TMP, "plan.xlsx")
    o = run([S("yt-plan", "plan_xlsx.py"), S("yt-plan", "examples", "plan.json"), "--out", out])
    import openpyxl
    wb = openpyxl.load_workbook(out)
    assert wb.sheetnames[:2] == ["برنامه", "وقت"]
    assert wb["برنامه"]["A3"].value == "۱۴۰۵/۰۸/۰۲", wb["برنامه"]["A3"].value
    assert "بیشتر از وقت" in o


@test("thumb: پنج چیدمان و برگهٔ مقایسه")
def _():
    od = os.path.join(TMP, "thumbs")
    specs = [S("yt-thumb", "examples", f"{n}.json") for n in ("bold", "split", "photo", "versus", "number")]
    run([S("yt-thumb", "thumb.py")] + specs + ["--out-dir", od, "--preview"])
    from PIL import Image
    for n in ("bold", "split", "photo", "versus", "number"):
        assert Image.open(os.path.join(od, n + ".png")).size == (1280, 720)
    assert os.path.exists(os.path.join(od, "preview.png"))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@test("publish: چک، تأیید دستی، آپلود ساختگی یوتیوب و آپارات، دفتر انتشار")
def _():
    if not shutil.which("ffmpeg"):
        raise AssertionError("ffmpeg برای ساخت ویدیوی آزمایشی لازم است")
    port = free_port()
    srv = subprocess.Popen([PY, os.path.join(T, "mock_api.py"), str(port)])
    try:
        time.sleep(0.8)
        base = f"http://127.0.0.1:{port}"
        env = dict(ENV, YTFA_TOKEN_URL=base + "/token", YTFA_API_BASE=base + "/api",
                   YTFA_UPLOAD_BASE=base + "/upload", YTFA_APARAT_BASE=base + "/aparat", YTFA_CHUNK="65536")
        run([S("yt-setup", "channel.py"), "new", "pub"], env=env)
        d = run([S("yt-setup", "channel.py"), "item", "--type", "video", "--title", "آزمایش",
                 "--date", "2099-01-01", "--time", "19:00"], env=env).strip()
        ch = os.path.dirname(os.path.dirname(d))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "4", "-c:v", "libx264", "-preset",
                        "veryfast", "-c:a", "aac", "-shortest", "-y", os.path.join(d, "video.mp4")], check=True)
        meta = {"title": "عنوان <بد>", "description": "توضیح", "tags": ["الف"]}
        json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
        run([S("yt-publish", "publish.py"), "check", d], ok_codes=(1,), env=env)       # < > رد شود
        meta["title"] = "عنوان آزمایشی"
        json.dump(meta, open(os.path.join(d, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
        run([S("yt-publish", "publish.py"), "approve", d, "--auto"], ok_codes=(2,), env=env)  # حالت دستی
        run([S("yt-publish", "publish.py"), "approve", d, "--approved-by", "بله"], env=env)
        assert os.path.exists(os.path.join(ch, "ready", os.path.basename(d), "انتشار.md"))
        sys.path.insert(0, S("yt-publish"))
        os.environ.update(env)
        import settings
        sec = {"youtube": {"client_id": "c", "client_secret": "s", "refresh_token": "R"},
               "aparat": {"user": "u", "ltoken": "L"}}
        settings.save_secrets(ch, sec)
        cfg = settings.load(ch)
        cfg["category_aparat"] = 7
        settings.save(ch, cfg)
        run([S("yt-publish", "publish.py"), "method", "--channel", ch, "--youtube", "api", "--aparat", "api"], env=env)
        out = run([S("yt-publish", "publish.py"), "due", "--channel", ch], env=env)
        assert "youtu.be/VID123" in out and "زمان‌بندی" in out, out          # یوتیوب زودتر و زمان‌بندی‌شده
        assert "aparat" not in out.lower(), out                               # آپارات هنوز وقتش نشده
        out = run([S("yt-publish", "publish.py"), "publish", d, "--only", "aparat"], env=env)
        assert "aparat.com/v/abc12" in out, out
        st = json.load(open(os.path.join(d, "status.json"), encoding="utf-8"))
        assert st["status"] == "posted", st["status"]
        assert st["platforms"]["youtube"]["status"] == "scheduled"
        rows = open(os.path.join(ch, "published.csv"), encoding="utf-8-sig").read().splitlines()
        assert len(rows) == 3, rows
        mode = oct(os.stat(settings.secrets_path(ch)).st_mode)[-3:]
        assert os.name == "nt" or mode == "600", mode
    finally:
        srv.terminate()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for name, status, msg in results:
        print(f"  {'✓' if status == 'PASS' else '✗'} {name}" + (f"\n      {msg}" if msg else ""))
    bad = [r for r in results if r[1] != "PASS"]
    print(f"\n{len(results) - len(bad)} از {len(results)} تست قبول شد." if not bad else
          f"\n{len(bad)} تست شکست خورد.")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
