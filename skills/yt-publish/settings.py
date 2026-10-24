"""
settings.py - تنظیمات انتشار هر کانال (publish.json) و فایل رمزها.

publish.json کنار channel.md در پوشهٔ کانال است و چیز محرمانه‌ای ندارد:
  {
    "mode": "manual" | "auto",          manual: هر ویدیو با «بله»ی صاحب کانال؛ auto: بعد از چک‌های فنی، بی‌سؤال
    "targets": ["youtube", "aparat"],   کجاها منتشر شود (پیش‌فرض برای هر ویدیو؛ meta.json هر ویدیو می‌تواند عوضش کند)
    "method": {"youtube": "manual" | "api", "aparat": "manual" | "api"},
    "privacy": "public" | "unlisted" | "private",     وضعیت ویدیو در یوتیوب بعد از انتشار
    "youtube_schedule": true,           ویدیوی تأییدشده زودتر آپلود شود و خود یوتیوب سر ساعت منتشرش کند
    "notify_subscribers": true,
    "made_for_kids": false,
    "ai_disclosure": true,              اگر ویدیو محتوای ساختگیِ واقع‌نما دارد، اعلام شود (containsSyntheticMedia)
    "category_youtube": "27",           شمارهٔ دستهٔ یوتیوب (۲۷ آموزش، ۲۸ علم و فناوری، ۲۲ مردم و وبلاگ)
    "category_aparat": 0                شمارهٔ دستهٔ آپارات (با aparat_api.py categories ببین)
  }

رمزها (توکن یوتیوب، توکن آپارات) در فایل جدا:
  <خانهٔ کانال‌ها>/.secrets/<نام کانال>.json
که فقط برای کاربر خود سیستم خواندنی است. این فایل را هیچ‌وقت در گیت، گفتگو یا جای عمومی نگذار.
"""

import json
import os
import stat

DEFAULTS = {
    "mode": "manual",
    "targets": ["youtube", "aparat"],
    "method": {"youtube": "manual", "aparat": "manual"},
    "privacy": "public",
    "youtube_schedule": True,
    "notify_subscribers": True,
    "made_for_kids": False,
    "ai_disclosure": True,
    "category_youtube": "27",
    "category_aparat": 0,
}
MODES = {"manual": "دستی (با تأیید تو)", "auto": "خودکار (بدون پرسیدن)"}
METHODS = {"manual": "خودت آپلود می‌کنی", "api": "آپلود خودکار"}
PLATFORM_FA = {"youtube": "یوتیوب", "aparat": "آپارات"}


def path(channel):
    return os.path.join(channel, "publish.json")


def load(channel):
    cfg = json.loads(json.dumps(DEFAULTS))
    p = path(channel)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            user = json.load(f)
        # سازگاری با publish.json قدیمی که method یک رشته بود
        if isinstance(user.get("method"), str):
            user["method"] = {"youtube": user["method"], "aparat": "manual"}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


def save(channel, cfg):
    with open(path(channel), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def secrets_path(channel):
    channel = os.path.abspath(channel)
    return os.path.join(os.path.dirname(channel), ".secrets", os.path.basename(channel) + ".json")


def secrets(channel):
    p = secrets_path(channel)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_secrets(channel, data):
    p = secrets_path(channel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    os.replace(tmp, p)
