# راهنمای ساخت، نصب و تست — نسخه‌ی آفلاین

> **نسخه‌ی هدف:** 3.4.2 (arm64-v8a) · **پکیج:** `com.paeezanstudio.pesarkhande`
> **نوع خروجی:** یک APK تکی (base + کتابخانه‌های بومی ادغام‌شده)

---

## ۱. پیش‌نیازها

| نیاز | حداقل | توضیح |
|------|-------|-------|
| سیستم | Linux / macOS / Windows (یا WSL) | فقط برای ساخت؛ بازی روی گوشی اجرا می‌شود |
| Python | **3.9+** | هنگام نصب در ویندوز گزینه‌ی «Add python.exe to PATH» را بزنید |
| اینترنت | فقط بار اول | نصب یک بسته‌ی PyPI (`cryptography`) |
| OpenSSL | **لازم نیست** | اگر روی سیستم باشد برای امضای v1 استفاده می‌شود؛ در غیر این صورت مسیر جایگزین داخلی فعال می‌شود |
| دستگاه | Android 6.0+ (API 23) | **arm64** (همه‌ی گوشی‌های متوسط به بالا) |

> **اوبونتو/دبیان:** اگر `python3 -m venv` خطا داد، بسته‌ی `python3-venv` را نصب کنید
> (`sudo apt install python3-venv`).

---

## ۲. دریافت فایل‌های اصلی

دو فایل از نسخه‌ی **۳.۴.۲** بازی لازم است:

| فایل | حجم (بایت) | SHA-256 |
|------|-----------:|---------|
| `base.apk` | 129,977,246 | `94a9beca7ae0025062bb1f5ed76541e8a7d1df41054cc491b1b9f5325d67643b` |
| `split_config.arm64_v8a.apk` | 27,993,663 | `e47f734399c489d92b65270a141603e80eb956fac1a086d6ec1efb2ee4b29370` |

### ۲.۱. از کجا؟ — روش پیشنهادی: از روی گوشی
بازی را از **کافه‌بازار** روی گوشی نصب کنید (نسخه‌ی ۳.۴.۲)، سپس فایل‌ها را با `adb` بیرون بکشید:

```bash
adb shell pm path com.paeezanstudio.pesarkhande
# package:/data/app/~~xxxx/com.paeezanstudio.pesarkhande-xxxx/base.apk
# package:/data/app/~~xxxx/com.paeezanstudio.pesarkhande-xxxx/split_config.arm64_v8a.apk
# package:...split_config.fa.apk  و ...

mkdir -p original
adb pull /data/app/~~xxxx/.../base.apk                     original/pesarkhande-3.4.2-base.apk
adb pull /data/app/~~xxxx/.../split_config.arm64_v8a.apk   original/pesarkhande-3.4.2-split_config.arm64_v8a.apk
```
فقط این دو فایل لازم است؛ بقیه‌ی splitها (زبان/تراکم پیکسل) لازم نیستند.

### ۲.۲. روش دیگر: وب‌سایت‌های میرور
سایت‌هایی مثل APKPure/APKMirror نسخه‌ی XAPK (شامل base + split) دارند. فایل XAPK در واقع یک ZIP
است؛ `base.apk` و `split_config.arm64_v8a.apk` را از داخلش خارج کنید. مطمئن شوید نسخه
**3.4.2** با `versionCode 3420004` باشد.

### ۲.۳. بررسی درستی فایل‌ها
```bash
sha256sum original/*.apk            # Linux / macOS
certutil -hashfile original\pesarkhande-3.4.2-base.apk SHA256    # Windows
```
اگر هش‌ها با جدول بالا نمی‌خواند، نسخه‌ی دیگری گرفته‌اید — پچ احتمالاً کار نمی‌کند
(پچ با «جستجوی رشته» انجام می‌شود و اگر رشته پیدا نشود، build با خطا متوقف می‌شود، نه خروجی خراب).

فایل‌ها را در `original/` بگذارید. نام دلخواه است، فقط باید کلمه‌ی `base` و `split`+`arm64` را داشته باشند:

```
original/pesarkhande-3.4.2-base.apk
original/pesarkhande-3.4.2-split_config.arm64_v8a.apk
```

> `original/` در `.gitignore` است — فایل‌های بازی هرگز وارد Git نمی‌شوند.

---

## ۳. ساخت

### Linux / macOS / WSL / Git Bash
```bash
chmod +x build.sh
./build.sh
```

### ویندوز (بدون WSL)
دو بار روی **`build.cmd`** کلیک کنید، یا در `cmd`:
```bat
build.cmd
```

اسکریپت خودش محیط مجازی `.tools/venv` را می‌سازد و `cryptography` را نصب می‌کند.
کلید امضای شخصی در `keys/` ساخته می‌شود — **نگهش دارید**؛ بروزرسانی‌های بعدی باید با
همان کلید امضا شوند تا روی نسخه‌ی قبلی نصب شوند.

خروجی (هر دو سیستم‌عامل):

```
out/pesarkhande-offline-arm64.apk
```

### گزینه‌ها
```bash
./build.sh --pair                 # خروجی base+split (برای SAI) به‌جای APK تکی
./build.sh BASE.apk SPLIT.apk     # مسیر دستی فایل‌ها
OUT=/tmp/build ./build.sh         # پوشه‌ی خروجی دلخواه
```

### اجرای دستی (بدون اسکریپت)
```bash
python3 -m pip install -r requirements.txt
python3 tools/patch.py build \
  --base original/pesarkhande-3.4.2-base.apk \
  --split original/pesarkhande-3.4.2-split_config.arm64_v8a.apk \
  --single --rename ConnectionScreen=MainMenu --out out/
```

### اجرای کامل در سندباکس (برای مقایسه)
```
[deps] ok (cryptography 50.0.2)
[1/4] patching metadata literals
  literal #4451: 'ConnectionScreen' -> 'MainMenu'
[2/4] patching manifest (isSplitRequired -> false)
[3/4] rebuilding APK with 16 native libraries
[4/4] signing
verify: v2 OK
```
زمان کل با ایجاد محیط مجازی از صفر: **۲۷ ثانیه**؛ حجم خروجی: **۱۵۷٬۹۶۵٬۷۵۳ بایت**.

---

## ۴. نصب

### حالت عادی
```bash
adb install out/pesarkhande-offline-arm64.apk
```
یا فایل را روی گوشی کپی کنید و از файл‌منیجر نصب کنید (فعال‌بودن «منابع ناشناس» لازم است).

### نکته‌ی مهم درباره‌ی امضا
APK اصلی با کلید **Paeezan Studio** امضا شده و خروجی ما با کلید **شخصی شما**.
بنابراین اگر بازی اصلی روی گوشی نصب است، اول باید **حذف** شود (داده‌هایش پاک می‌شود):

```bash
adb uninstall com.paeezanstudio.pesarkhande
```

---

## ۵. تست مرحله‌ای

هر مرحله را جدا آزمایش کنید و نتیجه را یادداشت کنید:

| # | آزمون | انتظار |
|---|-------|--------|
| T1 | نصب بدون خطا | `Success` |
| T2 | باز کردن برنامه | لوگو → لودینگ → **منوی اصلی** (بدون صفحه‌ی اتصال) |
| T3 | حالت هواپیما | منو بالا بیاید، هیچ درخواست شبکه‌ای نرود |
| T4 | ری‌استارت برنامه | منو دوباره بالا بیاید |
| T5 | ورود به نبرد | آیا نبرد شروع می‌شود؟ (احتمالاً خیر — ببینید چه پیامی می‌دهد) |
| T6 | خاموش/روشن دستگاه | برنامه و پیشرفت حفظ شود |

### اگر T2 شکست خورد — گزارش خودکار
گوشی را با USB وصل کنید (USB debugging روشن) و بعد از باز کردن بازی و دیدن مشکل اجرا کنید:

```bash
python3 tools/diagnose.py            # لاگ را پاک می‌کند، بازی را باز می‌کند، ۲۵ ثانیه ضبط می‌کند
python3 tools/diagnose.py --seconds 60 --no-launch
```
یک فایل `diagnose-<تاریخ>.txt` ساخته می‌شود: مشخصات گوشی، نسخه‌ی نصب‌شده، کرش‌ها با stack trace،
خطاهای صحنه و تلاش‌های شبکه. **همان فایل را بفرستید.** اگر `adb` ندارید، از برنامه‌ی
Matlog/L Logcat Reader خروجی بگیرید و `--logcat FILE` بدهید.

- **کرش فوری:** در گزارش بخش `[crashes]` با آدرس‌های `pc ... libil2cpp.so` هست؛ این آدرس‌ها
  برای ما به متد دقیق C# نگاشت می‌شوند.
- **ماندن روی لودینگ:** احتمالاً `LoadingScreen` منتظر دانلود AssetBundle است؛
  در حالت آفلاین باید مسیر جایگزین پیدا شود (مرحله‌ی بعدی پروژه).
- **منوی خالی/کرش در منو:** پروفایل از سرور نمی‌آید؛ باید پروفایل محلی تزریق شود.

---

## ۶. بکاپ و بازیابی

### بکاپ از پیشرفت
داده‌ی بازی در دستگاه ذخیره می‌شود (PlayerPrefs / فایل‌های برنامه):

```bash
adb backup -f mafiaso-backup.ab com.paeezanstudio.pesarkhande
```

یا با دسترسی root:
```bash
adb shell tar -czf /sdcard/mafiaso-data.tar.gz /data/data/com.paeezanstudio.pesarkhande
adb pull /sdcard/mafiaso-data.tar.gz .
```

### بازیابی
```bash
adb restore mafiaso-backup.ab
```

> تا وقتی ذخیره‌ی محلی (M4) پیاده نشود، بازی از پروفایل سرور استفاده می‌کند و
> «پیشرفت» معنایی ندارد. این بخش بعد از M4 تکمیل می‌شود.

---

## ۷. عیب‌یابی

| مشکل | علت محتمل | راه‌حل |
|------|-----------|--------|
| `INSTALL_FAILED_NO_MATCHING_ABIS` | گوشی arm64 نیست | نسخه‌ی armv7 لازم است (پشتیبانی نمی‌شود) |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | امضای متفاوت | حذف نسخه‌ی اصلی، سپس نصب |
| `INSTALL_PARSE_FAILED_NO_CERTIFICATES` | امضا خراب | `python3 tools/apk.py verify --in out/....apk` |
| نصب می‌شود ولی کرش می‌کند | پچ ناسازگار | `adb logcat` بفرستید |
| صفحه‌ی سیاه | AssetBundle راه‌دور | نیاز به M3 |
| `python3: command not found` / `'python' is not recognized` | پایتون نصب نیست یا در PATH نیست | از python.org نصب کنید و «Add to PATH» را بزنید |
| `ensurepip is not available` | بسته‌ی venv نصب نیست (دبیان/اوبونتو) | `sudo apt install python3-venv` |
| `pip` نمی‌تواند `cryptography` را نصب کند | فیلتر/بدون اینترنت | یک بار با VPN/پروکسی اجرا کنید؛ بار اول فقط |

---

## ۸. بازگرداندن تغییرات

هیچ فایل اصلی تغییر نمی‌کند. برای بازگشت:
- پوشه‌ی `out/` را پاک کنید.
- نسخه‌ی اصلی را از کافه‌بازار نصب کنید.

همه‌ی پچ‌ها در `tools/patch.py` و قابل حذف/تغییر هستند.
