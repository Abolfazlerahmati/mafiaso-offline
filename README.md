# Mafiaso Offline — نسخه‌ی شخصی و آفلاین «پسرخوانده»

بازسازی نسخه‌ی آفلاین بازی اندرویدی **پسرخوانده / Mafioso** (پکیج
`com.paeezanstudio.pesarkhande`، نسخه‌ی 3.4.2) با حفظ موتور، UI و منابع اصلی.

> ⚠️ این پروژه برای استفاده‌ی **شخصی** است. منابع بازی متعلق به Paeezan Studio است
> و بازنشر عمومی آن مجاز نیست.

## شروع سریع

> اولین بار اینجایی؟ [`docs/00-quickstart.md`](docs/00-quickstart.md) — از دانلود از GitHub تا اجرای بازی، گام‌به‌گام.


```bash
# 1) ریپو را بگیرید و وارد آن شوید
git clone https://github.com/Abolfazlerahmati/mafiaso-offline.git
cd mafiaso-offline

# 2) دو فایل اصلی بازی را بگیرید (از تگ apk-parts)
./get-apks.sh          # ویندوز: get-apks.cmd

# 3) بسازید
./build-all.sh         # هر پنج واریانت (A..E) — یا فقط A: ./build.sh
                       # ویندوز: build.cmd (فقط A)

# 4) نصب
adb install out/pesarkhande-offline-arm64.apk
```

| بیلد | پوشه | چه چیزی را ثابت می‌کند |
|------|------|------------------------|
| A | `out/` | منو بدون صفحه‌ی اتصال بالا می‌آید؟ |
| B | `out-native/` | همان A با پچ کد بومی |
| C | `out-battle/` | ورود به `Arena_1` ممکن است؟ |
| D | `out-debug/` | GUI دیباگ خودِ بازی در آرنا (دکمه‌ی «Start Battle») |
| E | `out-bot/` | نبرد با بات خودکار شروع می‌شود؟ |

پیش‌نیاز: فقط Python 3.9+ و (بار اول) اینترنت برای نصب `cryptography`. OpenSSL لازم نیست.

## مستندات

| فایل | محتوا |
|------|-------|
| [`docs/00-quickstart.md`](docs/00-quickstart.md) | **از صفر تا اجرا** — دانلود، ساخت، نصب، تست |
| [`ruls.md`](ruls.md) | قوانین و قراردادهای پروژه |
| [`status.md`](status.md) | وضعیت جاری، هش‌ها، مایل‌ستون‌ها |
| [`docs/01-technical-report.md`](docs/01-technical-report.md) | تحلیل فنی کامل بازی (مرحله ۱) |
| [`docs/02-architecture.md`](docs/02-architecture.md) | معماری نسخه‌ی آفلاین (مرحله ۲) |
| [`docs/03-toolchain.md`](docs/03-toolchain.md) | ابزارهای IL2CPP و امضای APK (M1) |
| [`docs/04-install-guide.md`](docs/04-install-guide.md) | ساخت، نصب، تست، بکاپ |
| [`docs/05-feature-report.md`](docs/05-feature-report.md) | قابلیت‌ها و محدودیت‌ها |
| [`tools/`](tools/) | `il2cpp.py` (پارسر)، `xref.py` (ارجاع استاتیک + دیس‌اسمبل)، `apk.py` (بازسازی/امضا)، `axml.py` (manifest)، `patch.py` (پچ + build)، `diagnose.py` (گزارش کرش از گوشی) |

## وضعیت

زنجیره‌ی ابزار کامل است و یک APK تکی (base + ۱۶ کتابخانه‌ی بومی، امضای v1/v2/v3)
ساخته می‌شود. پنج بیلد آزمایشی (A..E) برای بوت آفلاین و نبرد با بات وجود دارد —
همه **آزمون‌نشده‌اند** و باید روی گوشی تأیید شوند.
**بازی هنوز آفلاین قابل بازی نیست** — برای جزئیات و نقشه‌ی ادامه‌ی کار
به [`docs/05-feature-report.md`](docs/05-feature-report.md) مراجعه کنید.
