#!/usr/bin/env python3
"""
yt_api.py - اتصال به YouTube Data API v3 برای آپلود ویدیو، تامبنیل و زمان‌بندی انتشار.

فقط کتابخانهٔ استاندارد پایتون. مستندات: developers.google.com/youtube/v3

پیش‌نیاز (یک بار؛ راهنمای قدم‌به‌قدم در yt-publish/API-SETUP.md):
  یک پروژه در Google Cloud با «YouTube Data API v3» فعال، صفحهٔ رضایت OAuth، و یک
  «OAuth client ID» از نوع Desktop app که فایل JSON آن (client_secret_....json) را دانلود کرده‌ای.

دستورها:
  python yt_api.py login  --channel <کانال> --client-secret <فایل json>   مرورگر باز می‌شود؛ اجازه بده
  python yt_api.py status --channel <کانال>      کانال وصل‌شده و سلامت توکن
  python yt_api.py logout --channel <کانال>

ورود با روش «loopback» گوگل انجام می‌شود: مرورگر خودت صفحهٔ گوگل را باز می‌کند، اجازه می‌دهی و گوگل
به یک آدرس محلی روی همین کامپیوتر (127.0.0.1) برمی‌گردد. رمز گوگل تو هیچ‌وقت به این ابزار داده نمی‌شود؛
فقط «توکن تمدید» در فایل رمزهای همان کانال ذخیره و هرگز چاپ نمی‌شود.

اینترنت: اگر برای دسترسی به گوگل فیلترشکن یا پراکسی لازم داری، پایتون از متغیرهای HTTPS_PROXY و
HTTP_PROXY استفاده می‌کند (مثلاً set HTTPS_PROXY=http://127.0.0.1:10809).
"""

import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets as pysecrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import settings  # noqa: E402

AUTH_URL = os.environ.get("YTFA_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth")
TOKEN_URL = os.environ.get("YTFA_TOKEN_URL", "https://oauth2.googleapis.com/token")
API = os.environ.get("YTFA_API_BASE", "https://www.googleapis.com/youtube/v3")
UPLOAD = os.environ.get("YTFA_UPLOAD_BASE", "https://www.googleapis.com/upload/youtube/v3")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
UA = "youtube-fa/1.0"
CHUNK = int(os.environ.get("YTFA_CHUNK", 8 * 1024 * 1024))


class ApiError(Exception):
    def __init__(self, msg, status=None, reason=None, transient=False):
        super().__init__(msg)
        self.status, self.reason, self.transient = status, reason, transient


HINTS = {
    "quotaExceeded": "سهمیهٔ روزانهٔ API تمام شده؛ فردا (به وقت اقیانوس آرام) دوباره امتحان می‌شود",
    "uploadLimitExceeded": "سقف آپلود روزانهٔ این کانال پر شده",
    "forbidden": "دسترسی نیست؛ با همان حساب صاحب کانال login کن",
    "insufficientPermissions": "دسترسی کافی نیست؛ دوباره login کن و همهٔ اجازه‌ها را تیک بزن",
    "invalidTitle": "عنوان نامعتبر است (خالی، بیش از ۱۰۰ حرف، یا < و >)",
    "invalidDescription": "توضیحات نامعتبر است (بیش از ۵۰۰۰ بایت، یا < و >)",
    "invalidTags": "تگ‌ها نامعتبرند (مجموع بیش از ۵۰۰ حرف؟)",
    "invalidPublishAt": "زمان انتشار نامعتبر است؛ باید در آینده باشد",
    "invalid_grant": "توکن باطل شده یا منقضی است؛ yt_api.py login را دوباره اجرا کن. "
                     "اگر هر هفته تکرار می‌شود، صفحهٔ رضایت OAuth را از Testing به In production ببر (API-SETUP.md)",
}


def _err(body, status):
    try:
        j = json.loads(body)
    except ValueError:
        return ApiError(f"HTTP {status}: {body[:300]}", status=status, transient=status >= 500)
    if "error" in j and isinstance(j["error"], str):          # خطای سرور توکن
        r = j["error"]
        return ApiError(f"{r}: {j.get('error_description', '')} {HINTS.get(r, '')}".strip(), status, r)
    e = j.get("error", {})
    errs = e.get("errors") or [{}]
    reason = errs[0].get("reason") or e.get("status")
    msg = e.get("message") or body[:300]
    transient = status >= 500 or reason in ("backendError", "rateLimitExceeded", "userRateLimitExceeded")
    hint = HINTS.get(reason, "")
    return ApiError(f"{msg}" + (f" ({hint})" if hint else "") + f" [{reason}]", status, reason, transient)


def request(method, url, data=None, headers=None, timeout=120, tries=4):
    last = None
    for k in range(tries):
        req = urllib.request.Request(url, data=data, method=method, headers=dict({"User-Agent": UA}, **(headers or {})))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 308:                                  # پاسخ «ادامه بده» آپلود تکه‌ای
                return 308, dict(e.headers), b""
            err = _err(body, e.code)
            if not err.transient or k == tries - 1:
                raise err
            last = err
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = ApiError(f"شبکه: {e}؛ اینترنت یا فیلترشکن را بررسی کن", transient=True)
            if k == tries - 1:
                raise last
        time.sleep(2 ** k * 3)
    raise last


# ---------------------------------------------------------------- OAuth

def _client(path):
    with open(path, encoding="utf-8") as f:
        j = json.load(f)
    c = j.get("installed") or j.get("web") or j
    if "client_id" not in c:
        raise SystemExit("این فایل client secret گوگل نیست (کلید installed.client_id ندارد).")
    return {"client_id": c["client_id"], "client_secret": c.get("client_secret", "")}


def login(channel, client_secret, port=0, open_browser=True):
    cl = _client(client_secret)
    verifier = base64.urlsafe_b64encode(pysecrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = pysecrets.token_urlsafe(16)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            ok = "code" in got and got.get("state") == state
            msg = "اتصال انجام شد. این صفحه را ببند و به Claude برگرد." if ok else "اتصال انجام نشد؛ دوباره امتحان کن."
            body = f"<html dir='rtl'><meta charset='utf-8'><body style='font:20px tahoma;padding:40px'>{msg}</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": cl["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state})
    print("این آدرس را در مرورگر باز کن (اگر خودش باز نشد) و با حساب صاحب کانال اجازه بده:\n")
    print(url + "\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    t.join(timeout=300)
    srv.server_close()
    if got.get("state") != state or "code" not in got:
        raise SystemExit("اجازه داده نشد یا زمانش (۵ دقیقه) تمام شد: " + got.get("error", "بی‌پاسخ"))
    _, _, body = request("POST", TOKEN_URL, urllib.parse.urlencode({
        "code": got["code"], "client_id": cl["client_id"], "client_secret": cl["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"})
    tok = json.loads(body)
    if "refresh_token" not in tok:
        raise SystemExit("گوگل توکن تمدید نداد؛ در myaccount.google.com/permissions دسترسی این اپ را بردار و دوباره login کن.")
    sec = settings.secrets(channel)
    sec["youtube"] = {"client_id": cl["client_id"], "client_secret": cl["client_secret"],
                      "refresh_token": tok["refresh_token"], "access_token": tok.get("access_token"),
                      "expires_at": time.time() + int(tok.get("expires_in", 3000)) - 60, "saved": time.strftime("%Y-%m-%d")}
    settings.save_secrets(channel, sec)
    return sec["youtube"]


def access_token(channel):
    sec = settings.secrets(channel)
    y = sec.get("youtube")
    if not y:
        raise ApiError("یوتیوب به این کانال وصل نیست؛ اول: yt_api.py login --channel <کانال> --client-secret <فایل>",
                       reason="not_logged_in")
    if y.get("access_token") and y.get("expires_at", 0) > time.time() + 30:
        return y["access_token"]
    _, _, body = request("POST", TOKEN_URL, urllib.parse.urlencode({
        "client_id": y["client_id"], "client_secret": y["client_secret"],
        "refresh_token": y["refresh_token"], "grant_type": "refresh_token"}).encode(),
        {"Content-Type": "application/x-www-form-urlencoded"})
    tok = json.loads(body)
    y["access_token"] = tok["access_token"]
    y["expires_at"] = time.time() + int(tok.get("expires_in", 3000)) - 60
    sec["youtube"] = y
    settings.save_secrets(channel, sec)
    return y["access_token"]


def api_get(channel, path, params):
    tok = access_token(channel)
    _, _, body = request("GET", f"{API}/{path}?" + urllib.parse.urlencode(params),
                      headers={"Authorization": f"Bearer {tok}"})
    return json.loads(body)


def my_channel(channel):
    j = api_get(channel, "channels", {"part": "snippet,status", "mine": "true"})
    items = j.get("items") or []
    if not items:
        raise ApiError("این حساب گوگل کانال یوتیوب ندارد.")
    it = items[0]
    return {"id": it["id"], "title": it["snippet"]["title"],
            "longUploadsStatus": it.get("status", {}).get("longUploadsStatus")}


# ---------------------------------------------------------------- upload

def upload_video(channel, path, meta, log=print):
    """آپلود تکه‌ای (resumable). meta: snippet و status. خروجی: پاسخ videos.insert."""
    tok = access_token(channel)
    size = os.path.getsize(path)
    meta = dict(meta)
    q = {"uploadType": "resumable", "part": "snippet,status"}
    if meta.get("_notify") is False:
        q["notifySubscribers"] = "false"
    meta.pop("_notify", None)
    body = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    st, hd, _ = request("POST", f"{UPLOAD}/videos?" + urllib.parse.urlencode(q), body, {
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/*"})
    loc = {k.lower(): v for k, v in hd.items()}.get("location")
    if not loc:
        raise ApiError("یوتیوب آدرس آپلود نداد.")
    sent = 0
    last_pct = -10
    with open(path, "rb") as f:
        while sent < size:
            f.seek(sent)
            chunk = f.read(CHUNK)
            end = sent + len(chunk) - 1
            tok = access_token(channel)
            st, hd, resp = request("PUT", loc, chunk, {"Authorization": f"Bearer {tok}",
                                                     "Content-Length": str(len(chunk)),
                                                     "Content-Range": f"bytes {sent}-{end}/{size}"},
                                timeout=600)
            if st in (200, 201):
                return json.loads(resp)
            rng = {k.lower(): v for k, v in hd.items()}.get("range")
            sent = int(rng.split("-")[1]) + 1 if rng else 0
            pct = int(sent * 100 / size)
            if pct - last_pct >= 10:
                log(f"   آپلود یوتیوب: {pct}٪")
                last_pct = pct
    raise ApiError("آپلود کامل نشد.", transient=True)


def set_thumbnail(channel, video_id, image):
    tok = access_token(channel)
    ctype = "image/png" if image.lower().endswith(".png") else "image/jpeg"
    with open(image, "rb") as f:
        data = f.read()
    _, _, body = request("POST", f"{UPLOAD}/thumbnails/set?videoId={urllib.parse.quote(video_id)}", data,
                      {"Authorization": f"Bearer {tok}", "Content-Type": ctype})
    return json.loads(body)


def video_status(channel, video_id):
    j = api_get(channel, "videos", {"part": "status,processingDetails", "id": video_id})
    items = j.get("items") or []
    return items[0] if items else {}


# ---------------------------------------------------------------- CLI

def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="اتصال یوتیوب")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("login")
    p.add_argument("--channel", required=True)
    p.add_argument("--client-secret", required=True)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    p = sub.add_parser("status")
    p.add_argument("--channel", required=True)
    p = sub.add_parser("logout")
    p.add_argument("--channel", required=True)
    a = ap.parse_args()
    ch = os.path.abspath(a.channel)
    try:
        if a.cmd == "login":
            login(ch, a.client_secret, a.port, not a.no_browser)
            info = my_channel(ch)
            print(f"وصل شد: کانال «{info['title']}» ({info['id']})")
            if info.get("longUploadsStatus") not in (None, "allowed"):
                print("توجه: ویدیوهای بالای ۱۵ دقیقه هنوز برای این کانال باز نیست (تأیید شماره تلفن در youtube.com/verify)")
        elif a.cmd == "status":
            info = my_channel(ch)
            y = settings.secrets(ch).get("youtube", {})
            print(json.dumps({"connected": True, "channel": info["title"], "id": info["id"],
                              "long_uploads": info.get("longUploadsStatus"), "since": y.get("saved")},
                             ensure_ascii=False, indent=2))
        elif a.cmd == "logout":
            sec = settings.secrets(ch)
            sec.pop("youtube", None)
            settings.save_secrets(ch, sec)
            print("اتصال یوتیوب از این کانال پاک شد. (دسترسی اپ را در myaccount.google.com/permissions هم می‌توانی برداری.)")
    except ApiError as e:
        print(f"خطا: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
