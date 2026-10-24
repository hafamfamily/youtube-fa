#!/usr/bin/env python3
"""
aparat_api.py - آپلود ویدیو در آپارات با API عمومی قدیمی آپارات (etc/api).

⚠ تجربی: این API رسماً مستندسازی‌شده و پشتیبانی‌شده نیست؛ بر پایهٔ روشی است که کتابخانه‌های متن‌باز
(مثل aparat-python) استفاده کرده‌اند و ممکن است آپارات هر زمان عوضش کند. اگر کار نکرد، روش انتشار
آپارات را «دستی» بگذار؛ پوشهٔ ready/ همه‌چیز را برای آپلود دستی در آپارات آماده دارد.

دستورها:
  python aparat_api.py login  --channel <کانال>         نام کاربری و رمز آپارات را در ترمینال (نه در گفتگو) می‌پرسد
  python aparat_api.py status --channel <کانال>
  python aparat_api.py categories                        فهرست دسته‌های آپارات و شمارهٔ آن‌ها
  python aparat_api.py logout --channel <کانال>

رمز آپارات ذخیره نمی‌شود. فقط نام کاربری و «توکن ورود» (ltoken) که آپارات برمی‌گرداند در فایل رمزهای
کانال می‌ماند و هرگز چاپ نمی‌شود. API قدیمی آپارات رمز را به‌صورت هش‌شده در آدرس می‌گیرد؛ برای همین
بهتر است برای کانال آپارات رمز یکتا داشته باشی که جای دیگری استفاده نمی‌شود.
"""

import argparse
import getpass
import hashlib
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import settings  # noqa: E402

BASE = os.environ.get("YTFA_APARAT_BASE", "https://www.aparat.com/etc/api")
UA = "Mozilla/5.0 (youtube-fa)"


class AparatError(Exception):
    def __init__(self, msg, transient=False):
        super().__init__(msg)
        self.transient = transient


def get(path, timeout=60):
    url = f"{BASE}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise AparatError(f"HTTP {e.code} از آپارات", transient=e.code >= 500)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise AparatError(f"شبکه: {e}", transient=True)
    try:
        return json.loads(raw)
    except ValueError:
        raise AparatError("پاسخ آپارات JSON نبود؛ احتمالاً API عوض شده. روش انتشار آپارات را دستی بگذار.")


def hash_pass(pw):
    return hashlib.sha1(hashlib.md5(pw.encode("utf-8")).hexdigest().encode("utf-8")).hexdigest()


def login(channel, user, pw):
    j = get(f"login/luser/{urllib.parse.quote(user)}/lpass/{hash_pass(pw)}")
    lg = j.get("login") or {}
    tok = lg.get("ltoken")
    if not tok:
        raise AparatError("ورود به آپارات انجام نشد: " + str(lg.get("value") or lg.get("type") or j)[:200])
    sec = settings.secrets(channel)
    sec["aparat"] = {"user": lg.get("username") or user, "ltoken": tok, "saved": time.strftime("%Y-%m-%d")}
    settings.save_secrets(channel, sec)
    return sec["aparat"]


def creds(channel):
    a = settings.secrets(channel).get("aparat")
    if not a:
        raise AparatError("آپارات به این کانال وصل نیست؛ اول: aparat_api.py login --channel <کانال>")
    return a


def categories():
    j = get("categories")
    return [(c.get("id"), c.get("name")) for c in (j.get("categories") or [])]


class _Multipart:
    """بدنهٔ multipart که فایل بزرگ را تکه‌تکه می‌خواند، نه یک‌جا در حافظه."""

    def __init__(self, fields, file_field, path):
        self.b = uuid.uuid4().hex
        pre = b""
        for k, v in fields.items():
            pre += (f"--{self.b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n").encode() \
                + str(v).encode("utf-8") + b"\r\n"
        ctype = mimetypes.guess_type(path)[0] or "video/mp4"
        pre += (f"--{self.b}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
                f"filename=\"{os.path.basename(path)}\"\r\nContent-Type: {ctype}\r\n\r\n").encode("utf-8")
        self.parts = [pre, path, f"\r\n--{self.b}--\r\n".encode()]
        self.length = len(pre) + os.path.getsize(path) + len(self.parts[2])
        self._i, self._f = 0, None
        self.sent = 0

    def read(self, n=-1):
        n = 1 << 20 if n is None or n < 0 else n
        while self._i < len(self.parts):
            p = self.parts[self._i]
            if isinstance(p, bytes):
                self._i += 1
                self.sent += len(p)
                return p
            if self._f is None:
                self._f = open(p, "rb")
            chunk = self._f.read(n)
            if chunk:
                self.sent += len(chunk)
                return chunk
            self._f.close()
            self._f = None
            self._i += 1
        return b""


def upload(channel, path, title, category, tags=None, descr="", allow_comment=True, log=print):
    a = creds(channel)
    j = get(f"uploadform/luser/{urllib.parse.quote(a['user'])}/ltoken/{a['ltoken']}")
    form = j.get("uploadform") or {}
    action, frm = form.get("formAction"), form.get("frm-id")
    if not action or not frm:
        raise AparatError("آپارات فرم آپلود نداد (توکن منقضی؟): " + str(form.get("value") or form)[:200]
                          + " — aparat_api.py login را دوباره اجرا کن.")
    fields = {"frm-id": frm, "data[title]": title, "data[category]": category,
              "data[tags]": ",".join(t.replace(",", " ") for t in (tags or [])),
              "data[comment]": "yes" if allow_comment else "no", "data[descr]": descr}
    body = _Multipart(fields, "video", path)
    req = urllib.request.Request(action, data=body, method="POST", headers={
        "User-Agent": UA, "Content-Type": f"multipart/form-data; boundary={body.b}",
        "Content-Length": str(body.length)})
    log(f"   آپلود آپارات: {os.path.getsize(path) / 1e6:.0f} مگابایت…")
    try:
        with urllib.request.urlopen(req, timeout=3600) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise AparatError(f"HTTP {e.code} هنگام آپلود در آپارات", transient=e.code >= 500)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise AparatError(f"شبکه هنگام آپلود: {e}", transient=True)
    try:
        res = json.loads(raw).get("uploadpost") or {}
    except ValueError:
        raise AparatError("پاسخ آپلود آپارات قابل خواندن نبود: " + raw[:200])
    uid = res.get("uid")
    if not uid:
        raise AparatError("آپارات آپلود را نپذیرفت: " + str(res.get("value") or res)[:200])
    return {"uid": uid, "url": f"https://www.aparat.com/v/{uid}"}


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="اتصال آپارات (تجربی)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("login", "status", "logout"):
        p = sub.add_parser(c)
        p.add_argument("--channel", required=True)
    sub.add_parser("categories")
    a = ap.parse_args()
    try:
        if a.cmd == "categories":
            for i, n in categories():
                print(f"{i:>4}  {n}")
            return
        ch = os.path.abspath(a.channel)
        if a.cmd == "login":
            user = input("نام کاربری آپارات: ").strip()
            pw = getpass.getpass("رمز آپارات (دیده نمی‌شود): ")
            r = login(ch, user, pw)
            print(f"وصل شد: {r['user']}")
        elif a.cmd == "status":
            c = creds(ch)
            j = get(f"uploadform/luser/{urllib.parse.quote(c['user'])}/ltoken/{c['ltoken']}")
            ok = bool((j.get("uploadform") or {}).get("formAction"))
            print(json.dumps({"user": c["user"], "since": c.get("saved"), "upload_ready": ok},
                             ensure_ascii=False, indent=2))
        elif a.cmd == "logout":
            sec = settings.secrets(ch)
            sec.pop("aparat", None)
            settings.save_secrets(ch, sec)
            print("اتصال آپارات از این کانال پاک شد.")
    except AparatError as e:
        print(f"خطا: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
