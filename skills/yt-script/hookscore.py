#!/usr/bin/env python3
"""
hookscore.py - امتیاز دادن به قلاب ویدیوی یوتیوب (۱۵ ثانیهٔ اول) پیش از اینکه یک برداشت را هدر بدهی.

بر پایهٔ hookscore.py از youtube-agent-skill (Jake Schincariol, MIT) و موتور فارسی instagram-fa؛
بازنویسی‌شده برای فارسی گفتاری (نیم‌فاصله، رقم فارسی، عدد گفتاری، جمله‌های مخلوط با اسم لاتین).

پنج سنجه، هر کدام ۰ تا ۱۰۰:
  مشخص‌بودن   عدد، مبلغ، زمان، اسم؛ منهای صفت‌های توخالی و کلمه‌های پرکننده
  خطاب        بیننده مخاطب است («تو»، «شما»، فعل دوم‌شخص)، ترجیحاً در شش کلمهٔ اول
  تنش         چیزی در خطر است (ضرر، اشتباه، نکن، قبل از اینکه...)
  کنجکاوی     سؤالی باز می‌ماند که بیننده نمی‌تواند ول کند؛ جمله‌ای که خودش جواب خودش را بدهد بسته است
  کوتاهی      ۹ تا ۲۶ کلمه؛ همان چیزی که در حدود ۱۰ ثانیه گفته می‌شود

جمع = ۶۰٪ میانگین + ۴۰٪ ضعیف‌ترین سنجه، منهای جریمهٔ «ردّی»ها (سلام، معرفی کانال، لایک و سابسکرایب...).
وزن ضعیف‌ترین حلقه عمدی است: قلابی با چهار سنجهٔ قوی و یک سنجهٔ مرده، از همان سنجهٔ مرده نشت می‌کند.

این چه نیست: پیش‌بین بازدید. قلاب بد (سلام‌واحوال، مقدمه، حرف کلی) را خوب از قلاب معقول جدا
می‌کند؛ بین دو قلاب خوب برنده را نمی‌تواند بگوید. امتیاز پایین دلیل دوباره نگاه کردن است؛ امتیاز
بالا قول نیست. نمودار ریتنشن واقعی را جدی‌تر بگیر.

استفاده:
  python hookscore.py hooks.txt                 # هر خط یک قلاب، رتبه‌بندی
  python hookscore.py --hook "یک جمله"
  python hookscore.py hooks.txt --json
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fa_text import (setup_stdout, words, low, numbers, latin_names, HASHTAG_RE,  # noqa: E402
                     EMOJI_RE, clamp, bar, normalize)

with open(os.path.join(HERE, "hooks.json"), encoding="utf-8") as _f:
    FORMULAS = json.load(_f)["hooks"]

WPS = 2.6           # کلمه در ثانیه، گفتار فارسی (~۱۵۵ کلمه در دقیقه)
BAND = (9, 26)      # حدود ۴ تا ۱۰ ثانیه گفتار

SPOKEN_NUMBERS = {
    "دو", "سه", "چهار", "پنج", "شش", "شیش", "هفت", "هشت", "نه", "ده", "دوازده", "پونزده",
    "پانزده", "بیست", "سی", "چهل", "پنجاه", "شصت", "هفتاد", "هشتاد", "نود", "صد", "دویست",
    "سیصد", "پونصد", "پانصد", "هزار", "میلیون", "میلیارد", "نصف", "دوبرابر", "سه‌برابر",
    "دوتا", "سه‌تا", "چهارتا", "پنج‌تا", "هفت‌تا", "ده‌تا", "صدتا", "نُه",
}
UNIT_WORDS = {
    "تومن", "تومان", "ریال", "دلار", "درصد", "دقیقه", "ثانیه", "ساعت", "روز", "هفته", "ماه",
    "سال", "مشترک", "سابسکرایبر", "بازدید", "ویو", "فالوور", "مشتری", "سفارش",
}
VAGUE = {
    "فوق‌العاده", "فوقالعاده", "باورنکردنی", "شگفت‌انگیز", "شگفت", "خفن", "جادویی", "انقلابی",
    "بی‌نظیر", "بینظیر", "عالی", "وحشتناک", "دیوانه‌کننده", "معجزه", "معجزه‌آسا", "کامل",
    "همه‌چیز", "همه‌چی", "قدرتمند", "حرفه‌ای", "نهایی", "رازهای", "بمب", "ترکوند", "ترکونده",
}
FILLER = {
    "واقعاً", "واقعا", "اصلاً", "اصلا", "یعنی", "مثلاً", "مثلا", "خب", "خوب", "دیگه", "کلاً", "کلا",
    "حالا", "بچه‌ها", "دوستان", "عزیزان", "سلام", "امروز", "ویدیو", "ویدئو", "کانال",
    "سابسکرایب", "لایک", "راستش", "درواقع", "به‌هرحال",
}
STAKES = {
    "نه", "نکن", "نکنید", "نزن", "نخر", "نذار", "نفرست", "هیچ‌وقت", "هرگز", "اشتباه", "اشتباهی",
    "غلط", "ضرر", "باختم", "سوخت", "سوختم", "هزینه", "گرون", "رایگان", "مجانی", "خطر",
    "خطرناک", "هشدار", "ممنوع", "دروغ", "پشیمون", "پشیمان", "حیف", "کلاهبرداری", "جریمه",
    "بدترین", "مشکل", "نمی‌دونستم", "نمیدونستم", "حذف", "قطع", "بلاک", "شکست", "خراب",
    "ول", "می‌میرن", "میمیرن", "می‌میره", "ریزش", "عقب", "قبل", "پیش", "بدون", "دیر",
}
NEG_VERB_RE = re.compile(r"^(?:ن(?:کن|زن|خر|ده|گو|فرست|ذار|گذار|ریز|خور|بین|نویس|ساز))")
CURIOUS = {
    "چرا", "چطور", "چطوری", "چگونه", "چی", "چیه", "چه", "کدوم", "کدام", "کدومش", "ولی", "اما",
    "تااینکه", "هیچ‌کس", "هیچکس", "تقریباً", "تقریبا", "جز", "به‌جز", "دلیل", "دلیلش", "راز",
    "نمی‌دونن", "نمیدونن", "نمی‌گن", "نمیگن", "عجیب", "برعکس", "ولی", "معلوم",
}
CLOSED_RE = re.compile(r"(?:چون|به خاطر اینکه|بخاطر اینکه|به این دلیل که|یعنی اینکه|که باعث می‌شه)")
YOU_RE = re.compile(r"(?:^|\s)(?:تو|شما|خودت|خودتون|خودتان|برات|براتون|بهت|بهتون|ازت|ازتون|"
                    r"باهات|باهاتون|you|your)(?=\s|$|[،,.!?؟])")
YOU_VERB_RE = re.compile(r"^(?:(?:می‌|می|نمی‌|نمی)\S{2,}(?:ی|ید|ین)|ن\S{2,}(?:دی|تی|دید|تید)|"
                         r"(?:ب|ن)\S{2,}ید|\S*(?:کردی|دادی|زدی|گرفتی|داری|دارید|هستی|هستید|نیستی|بودی))$")
# ضمیر ملکی «ـت/ـتون» (کانالت، ویدیوهات، موضوعتون) با واژه‌های عربیِ ـت (ساعت، قیمت) و فعل‌های
# گذشته (رفت، داشت) هم‌شکل است؛ پس محتاطانه و با وزن کمتر شمرده می‌شود.
POSS_RE = re.compile(r"^\S{2,}(?:هات|ت|تون|هاتون)$")
NOT_POSS_RE = re.compile(r"(?:است|ست|شت|فت|خت|قت|ات|یت|عت|مت|رت|بت|کت|ئت|وت|حالت|علت|دولت|ملت|"
                         r"خلوت|ثابت|ساعت|صورت)$")


def is_poss(word):
    if word.endswith(("هات", "هاتون", "تون")):
        return True
    return bool(POSS_RE.match(word)) and not NOT_POSS_RE.search(word)
IMPERATIVE_RE = re.compile(r"^(?:ب|ن)(?:کن|زن|خر|ده|گو|فرست|ذار|گذار|بین|ساز|نویس|خون|پرس)\S{0,3}$")

DEALBREAKERS = [
    (re.compile(r"^\s*(?:سلام|درود|عرض ادب|وقت(?:تون)? بخیر|hi |hey |hello )"),
     "سلام‌واحوال‌پرسی در قلاب. سلام را بعد از قلاب بگو، یا اصلاً نگو."),
    (re.compile(r"(?:به|ب) (?:کانال|چنل) .{0,25}خوش (?:اومدی|اومدید|آمدید)|من .{2,20} هستم"),
     "معرفی خودت یا کانال. بیننده هنوز دلیلی ندارد که بداند تو کیستی."),
    (re.compile(r"(?:لایک|سابسکرایب|سابسکرایپ|عضو (?:کانال|شو)|زنگوله)"),
     "درخواست لایک یا سابسکرایب در ۱۵ ثانیهٔ اول. هنوز به دست نیاورده‌ای."),
    (re.compile(r"(?:تو|توی|در) (?:این|اين) (?:ویدیو|ویدئو|قسمت)|"
                r"می‌خوام (?:بهتون|براتون) (?:بگم|نشون بدم|توضیح بدم)|میخوام بهتون|"
                r"قراره (?:بهتون|براتون)|قبل از (?:اینکه )?شروع"),
     "مقدمه. از خود نتیجه یا خود مشکل شروع کن."),
    (HASHTAG_RE, "هشتگ در متن گفتاری."),
    (EMOJI_RE, "ایموجی در متن گفتاری؛ این متن قرار است بلند خوانده شود."),
]

FIX = {
    "مشخص‌بودن": "یک صفت را با یک عدد، اسم یا تاریخ عوض کن",
    "خطاب": "«تو» یا «شما» را در شش کلمهٔ اول بیاور",
    "تنش": "بگو ادامه دادن به روش فعلی چه هزینه‌ای برای بیننده دارد",
    "کنجکاوی": "نیمه‌ای از جمله را که جواب خودش را می‌دهد حذف کن",
    "کوتاهی": "۹ تا ۲۶ کلمه. بلند بخوان و جایی که نفست تمام می‌شود قطع کن",
}
CHECKS = list(FIX)


def specificity(t):
    w = [low(x) for x in words(t)]
    if not w:
        return 0.0, "خالی"
    nums = numbers(t)
    names = set(latin_names(t))
    spoken = [x for x in w if x in SPOKEN_NUMBERS or x in UNIT_WORDS]
    vague = [x for x in w if x in VAGUE]
    filler = [x for x in w if x in FILLER]
    s = 34 + len(nums) * 22 + min(18, 9 * len(names)) + min(30, 12 * len(spoken)) \
        - len(vague) * 16 - len(filler) * 5
    found = nums[:2] + sorted(names)[:2] + spoken[:2]
    detail = (f"نشانه‌های مشخص: {'، '.join(found)}" if found else "نه عدد، نه اسم، نه زمان")
    if vague:
        detail += f"؛ صفت توخالی: {'، '.join(sorted(set(vague)))}"
    if filler:
        detail += f"؛ پرکننده: {'، '.join(sorted(set(filler))[:3])}"
    return clamp(s), detail


def address(t):
    w = [low(x) for x in words(t)]
    full = " " + normalize(t) + " "
    head = " " + " ".join(w[:6]) + " "
    n = len(YOU_RE.findall(full)) + sum(1 for x in w if YOU_VERB_RE.match(x))
    poss = sum(1 for x in w if is_poss(x))
    imp = any(IMPERATIVE_RE.match(x) for x in w)
    first = 30 if (YOU_RE.search(head) or any(YOU_VERB_RE.match(x) or IMPERATIVE_RE.match(x)
                                               or is_poss(x) for x in w[:6])) else 0
    n_all = n + poss
    s = 26 + min(3, n) * 20 + min(2, poss) * 12 + (14 if imp else 0) + first
    detail = "بیننده خطاب شده" + (" در شش کلمهٔ اول" if first else "، ولی دیر") if (n_all or imp) \
        else "بیننده خطاب نشده"
    return clamp(s), detail


def stakes(t):
    w = [low(x) for x in words(t)]
    hits = sorted({x for x in w if x in STAKES or NEG_VERB_RE.match(x)})
    has_num = bool(numbers(t)) or any(x in SPOKEN_NUMBERS for x in w)
    s = 22 + len(hits) * 26 + (14 if has_num else 0)
    return clamp(s), (f"نشانهٔ تنش: {'، '.join(hits[:4])}" if hits else "چیزی در خطر نیست")


def curiosity(t):
    w = [low(x) for x in words(t)]
    hits = [x for x in w if x in CURIOUS]
    hits += re.findall(r"تا (?:اینکه|وقتی)|قبل از اینکه|معلوم شد|فهمیدم که", normalize(t))
    q = 18 if re.search(r"[?؟]\s*$", t.strip()) else 0
    closed = -18 if CLOSED_RE.search(normalize(t)) else 0
    s = 24 + len(hits) * 17 + q + closed
    detail = (f"گره: {'، '.join(hits[:3])}" if hits else "گرهٔ بازی نیست")
    if closed:
        detail += "؛ جمله جواب خودش را می‌دهد («چون...»)"
    return clamp(s), detail


def brevity(t):
    n = len(words(t))
    secs = n / WPS
    lo, hi = BAND
    if n == 0:
        s = 0
    elif lo <= n <= hi:
        s = 100
    elif n < lo:
        s = max(30, 100 - (lo - n) * 11)
    else:
        s = max(10, 100 - (n - hi) * 7)
    return float(s), f"{n} کلمه، حدود {secs:.1f} ثانیه گفتار (بازهٔ خوب {lo} تا {hi} کلمه)"


def classify(t):
    tt = normalize(t)
    best, hits = None, 0
    for f in FORMULAS:
        n = sum(1 for p in f["match"] if re.search(p, tt, re.I))
        if n > hits:
            best, hits = f, n
    return (best["name"] if best else None), hits


def score(t):
    parts = {"مشخص‌بودن": specificity(t), "خطاب": address(t), "تنش": stakes(t),
             "کنجکاوی": curiosity(t), "کوتاهی": brevity(t)}
    vals = [v[0] for v in parts.values()]
    flags = [m for p, m in DEALBREAKERS if p.search(normalize(t))]
    total = clamp(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals) - 15 * len(flags))
    verdict = "قوی" if total >= 72 and not flags else ("قابل‌کار" if total >= 55 else "ضعیف")
    name, hits = classify(t)
    weakest = min(CHECKS, key=lambda k: parts[k][0])
    return {"hook": t.strip(), "checks": {k: {"score": round(v[0]), "detail": v[1]}
                                          for k, v in parts.items()},
            "score": round(total), "verdict": verdict, "formula": name, "matched": hits,
            "weakest": weakest, "fix": FIX[weakest], "flags": flags}


def report(r):
    print(f"\n  «{r['hook']}»")
    print("  " + "-" * 64)
    for k in CHECKS:
        c = r["checks"][k]
        print(f"    {k:<11} {bar(c['score'])} {c['score']:3d}   {c['detail']}")
    print(f"    {'جمع':<11} {bar(r['score'])} {r['score']:3d}   {r['verdict']}")
    print(f"    فرمول       " + (f"{r['formula']} ({r['matched']} الگو)" if r["formula"] else
                                "هیچ فرمولی نخورد؛ این معمولاً خلاصه است، نه قلاب"))
    for f in r["flags"]:
        print(f"    ردّی        {f}")
    print(f"    ضعیف‌ترین   {r['weakest']}: {r['fix']}")


def main():
    setup_stdout()
    ap = argparse.ArgumentParser(description="امتیاز قلاب ویدیوی یوتیوب")
    ap.add_argument("input", nargs="?", default=None, help="فایل (هر خط یک قلاب) یا - برای ورودی استاندارد")
    ap.add_argument("--hook", help="امتیاز یک قلاب")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.hook:
        lines = [a.hook]
    elif a.input:
        raw = sys.stdin.read() if a.input == "-" else open(a.input, encoding="utf-8").read()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
    else:
        ap.print_help()
        sys.exit(1)
    if not lines:
        print("چیزی برای امتیاز دادن نیست", file=sys.stderr)
        sys.exit(2)
    out = sorted((score(t) for t in lines), key=lambda r: -r["score"])
    if a.json:
        print(json.dumps(out if len(out) > 1 else out[0], ensure_ascii=False, indent=1))
        return
    for r in out:
        report(r)
    if len(out) > 1:
        print(f"\n  برنده: «{out[0]['hook']}» ({out[0]['score']}، {out[0]['verdict']})")
        if out[0]["score"] < 55:
            print("  حتی برنده زیر ۵۵ است؛ هیچ‌کدام هنوز قلاب نیستند.")
    print()


if __name__ == "__main__":
    main()
