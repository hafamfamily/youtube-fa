#!/usr/bin/env python3
"""
plan_xlsx.py - تبدیل برنامهٔ هفتگی یا ماهانهٔ یوتیوب (plan.json) به اکسل مرتب، رنگی، راست‌به‌چپ،
با تاریخ شمسی و قابل چاپ.

بر پایهٔ plan_xlsx.py از instagram-fa.

سه برگه:
  «برنامه»       هر ردیف یک ویدیو/شورتس؛ رنگ بر اساس نوع؛ ستون وضعیت با فهرست کشویی؛ ستون ساعت کار
  «وقت»          جمع ساعت کار در برابر وقت واقعی کاربر، با فرمول (اگر ساعت‌ها را عوض کنی، خودش حساب می‌کند)
  «راهنمای رنگ»

قالب plan.json:
{
  "channel": "نام کانال", "week_start": "2026-10-24", "hours_available": 7,
  "items": [{"date": "2026-10-24", "day": "شنبه", "time": "19:00", "type": "video",
             "platform": "both", "pillar": "...", "title": "...", "hook": "...", "thumb": "...",
             "hours": 6, "status": "ایده"}]
}
type: video | short | live | post     platform: youtube | aparat | both
اگر hours نباشد، تخمین پیش‌فرض نوع گذاشته می‌شود (ویدیو ۶، شورتس ۱، لایو ۲، پست ۰٫۳ ساعت).

پیش‌نیاز: pip install openpyxl
استفاده:  python plan_xlsx.py plan.json --out plan.xlsx
"""

import argparse
import json
import sys

TYPE_FA = {"video": "ویدیوی بلند", "short": "شورتس", "live": "لایو", "post": "پست انجمن"}
TYPE_COLOR = {"video": "DCEFEA", "short": "FDECD2", "live": "F9DEDC", "post": "E8EEF9"}
TYPE_HOURS = {"video": 6, "short": 1, "live": 2, "post": 0.3}
PLATFORM_FA = {"youtube": "یوتیوب", "aparat": "آپارات", "both": "یوتیوب + آپارات"}
STATUSES = ["ایده", "فیلم‌نامه", "ضبط", "تدوین", "منتظر تأیید", "تأییدشده", "منتشرشده"]


def g2j(gy, gm, gd):
    """تبدیل میلادی به شمسی (الگوریتم استاندارد)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + days // 31 if days < 186 else 7 + (days - 186) // 30
    jd = 1 + (days % 31 if days < 186 else (days - 186) % 30)
    return jy, jm, jd


FA_DIG = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def shamsi(iso):
    try:
        y, m, d = (int(x) for x in iso[:10].split("-"))
        jy, jm, jd = g2j(y, m, d)
        return f"{jy}/{jm:02d}/{jd:02d}".translate(FA_DIG)
    except Exception:
        return ""


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="برنامهٔ یوتیوب به اکسل")
    ap.add_argument("plan")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    try:
        from openpyxl import Workbook
        from openpyxl.formatting.rule import FormulaRule
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError:
        print("openpyxl نصب نیست: pip install openpyxl", file=sys.stderr)
        sys.exit(2)

    with open(a.plan, encoding="utf-8") as f:
        plan = json.load(f)

    font = "Vazirmatn"
    thin = Side(style="thin", color="C9CED6")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    accent = "B42318"   # قرمز یوتیوبی، کمی گرفته
    head_fill = PatternFill("solid", fgColor=accent)
    head_font = Font(name=font, bold=True, color="FFFFFF", size=11)
    body_font = Font(name=font, size=10)
    wrap = Alignment(horizontal="right", vertical="center", wrap_text=True, readingOrder=2)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True, readingOrder=2)

    def setup(ws, title, ncols):
        ws.sheet_view.rightToLeft = True
        ws.append([title])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
        c = ws.cell(1, 1)
        c.font = Font(name=font, bold=True, size=14, color=accent)
        c.alignment = center
        ws.row_dimensions[1].height = 30
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True

    wb = Workbook()
    ws = wb.active
    ws.title = "برنامه"
    headers = ["تاریخ", "روز", "ساعت", "نوع", "کجا", "ستون محتوا", "عنوان", "قلاب (جملهٔ اول)",
               "متن تامبنیل", "ساعت کار", "وضعیت"]
    setup(ws, f"برنامهٔ یوتیوب · {plan.get('channel', '')} · از {shamsi(plan.get('week_start', ''))}", len(headers))
    ws.append(headers)
    for j in range(1, len(headers) + 1):
        h = ws.cell(2, j)
        h.fill, h.font, h.alignment, h.border = head_fill, head_font, center, border
    ws.row_dimensions[2].height = 24
    items = plan.get("items", [])
    for p in items:
        t = p.get("type", "video")
        hours = p.get("hours", TYPE_HOURS.get(t, 1))
        ws.append([shamsi(p.get("date", "")) or p.get("date", ""), p.get("day", ""), p.get("time", ""),
                   TYPE_FA.get(t, t), PLATFORM_FA.get(p.get("platform", "both"), p.get("platform", "")),
                   p.get("pillar", ""), p.get("title", ""), p.get("hook", ""), p.get("thumb", ""),
                   hours, p.get("status", "ایده")])
        i = ws.max_row
        fill = PatternFill("solid", fgColor=TYPE_COLOR.get(t, "FFFFFF"))
        for j in range(1, len(headers) + 1):
            cell = ws.cell(i, j)
            cell.font, cell.border, cell.fill = body_font, border, fill
            cell.alignment = center if j in (1, 2, 3, 4, 5, 10, 11) else wrap
        ws.row_dimensions[i].height = 48
    last = ws.max_row
    for j, w in enumerate([12, 9, 8, 12, 14, 16, 32, 36, 18, 9, 13], 1):
        ws.column_dimensions[ws.cell(2, j).column_letter].width = w
    ws.freeze_panes = "A3"
    ws.print_title_rows = "2:2"
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    if items:
        dv.add(f"K3:K{last}")
        done = PatternFill("solid", fgColor="D1FADF")
        ws.conditional_formatting.add(f"K3:K{last}", FormulaRule(formula=['$K3="منتشرشده"'], fill=done))

    # برگهٔ وقت
    ws2 = wb.create_sheet("وقت")
    setup(ws2, "وقت لازم در برابر وقت واقعی", 2)
    avail = plan.get("hours_available")
    rows = [("جمع ساعت کار برنامه", f"=SUM(برنامه!J3:J{max(3, last)})"),
            ("وقت واقعی در این بازه (ساعت)", avail if avail is not None else ""),
            ("اختلاف", "=IF(B3=\"\",\"وقت واقعی را وارد کن\",B3-B2)"),
            ("نتیجه", "=IF(B3=\"\",\"\",IF(B2>B3,\"برنامه از وقتت بیشتر است؛ کمش کن\",\"در وقتت جا می‌شود\"))")]
    for k, (label, val) in enumerate(rows, 2):
        ws2.cell(k, 1, label)
        ws2.cell(k, 2, val)
        for j in (1, 2):
            c = ws2.cell(k, j)
            c.font, c.border = Font(name=font, size=11, bold=(j == 1)), border
            c.alignment = wrap if j == 1 else center
        ws2.row_dimensions[k].height = 26
    ws2.column_dimensions["A"].width = 30
    ws2.column_dimensions["B"].width = 34
    ws2.conditional_formatting.add("B5", FormulaRule(formula=['AND($B$3<>"",$B$2>$B$3)'],
                                                     fill=PatternFill("solid", fgColor="FEE4E2")))
    ws2.conditional_formatting.add("B5", FormulaRule(formula=['AND($B$3<>"",$B$2<=$B$3)'],
                                                     fill=PatternFill("solid", fgColor="D1FADF")))
    ws2.cell(7, 1, "ساعت‌های پیش‌فرض: ویدیوی بلند ۶، شورتس ۱، لایو ۲، پست ۰٫۳. ستون «ساعت کار» را با تجربهٔ خودت عوض کن.")
    ws2.merge_cells("A7:B7")
    ws2.cell(7, 1).font = Font(name=font, size=9, color="667085")
    ws2.cell(7, 1).alignment = wrap
    ws2.row_dimensions[7].height = 34

    ws3 = wb.create_sheet("راهنمای رنگ")
    ws3.sheet_view.rightToLeft = True
    for i, (t, c) in enumerate(TYPE_COLOR.items(), 1):
        ws3.cell(i, 1, TYPE_FA[t]).fill = PatternFill("solid", fgColor=c)
        ws3.cell(i, 1).font = body_font
        ws3.cell(i, 1).border = border
    ws3.column_dimensions["A"].width = 18

    wb.save(a.out)
    total = sum(p.get("hours", TYPE_HOURS.get(p.get("type", "video"), 1)) for p in items)
    msg = f"ساخته شد: {a.out}  ·  {len(items)} مورد، حدود {total:g} ساعت کار"
    if avail is not None:
        msg += f" از {avail:g} ساعت وقت" + ("  ⚠ بیشتر از وقت واقعی" if total > avail else "")
    print(msg)


if __name__ == "__main__":
    main()
