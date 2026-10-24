#!/usr/bin/env python3
"""
sync_fa_text.py - کپی کردن نسخهٔ اصلی fa_text.py در هر پوشهٔ اسکیلی که اسکریپت پایتون دارد.

چرا کپی؟ هر اسکیل باید به‌تنهایی هم کار کند (مثلاً وقتی کسی فقط یک پوشه را برمی‌دارد).
نسخهٔ اصلی: tools/fa_text.py — فقط همان را ویرایش کن و بعد این را اجرا کن.

  python tools/sync_fa_text.py          # کپی
  python tools/sync_fa_text.py --check  # فقط بررسی؛ اگر کپی‌ای قدیمی باشد، کد خروج ۱
"""

import filecmp
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER = os.path.join(ROOT, "tools", "fa_text.py")
SKILLS = os.path.join(ROOT, "skills")


def targets():
    for name in sorted(os.listdir(SKILLS)):
        d = os.path.join(SKILLS, name)
        if not os.path.isdir(d):
            continue
        scripts = [f for f in os.listdir(d) if f.endswith(".py") and f != "fa_text.py"]
        if any("fa_text" in open(os.path.join(d, f), encoding="utf-8").read() for f in scripts):
            yield os.path.join(d, "fa_text.py")


def main():
    check = "--check" in sys.argv
    stale = []
    for t in targets():
        if os.path.exists(t) and filecmp.cmp(MASTER, t, shallow=False):
            continue
        stale.append(t)
        if not check:
            shutil.copy(MASTER, t)
    for t in stale:
        print(("قدیمی: " if check else "به‌روز شد: ") + os.path.relpath(t, ROOT))
    if not stale:
        print("همهٔ کپی‌ها یکسان‌اند.")
    sys.exit(1 if (check and stale) else 0)


if __name__ == "__main__":
    main()
