# از صفر تا اجرا — راهنمای گام‌به‌گام

> این فایل از «هیچ فایلی ندارم» تا «بازی روی گوشی اجرا می‌شود» را پوشش می‌دهد.
> برای جزئیات بیشتر: [`04-install-guide.md`](04-install-guide.md) · برای وضعیت پروژه: [`../status.md`](../status.md)

## خلاصه‌ی ۶ خطی (اگر عجله داری)

```bash
git clone https://github.com/Abolfazlerahmati/mafiaso-offline.git
cd mafiaso-offline
git fetch origin refs/tags/apk-parts:refs/tags/apk-parts --force
mkdir -p original && git archive --format=tar refs/tags/apk-parts | tar -x -C original
rm -f original/part-* original/set.tar
./build-all.sh
```

بعد روی گوشی: `adb install out-debug/pesarkhande-offline-arm64.apk` و بازی را باز کن.

---

## ۰. پیش‌نیازها

| چی | چرا |
|----|-----|
| **Python 3.9+** | ابزار پچ و امضا. بار اول خودش `cryptography` را نصب می‌کند |
| **git** | گرفتن ریپو و فایل‌های اصلی |
| **~۲ گیگابایت** فضای آزاد | دو APK اصلی (۱۵۸ مگ) + خروجی‌ها (هر بیلد ۱۵۸ مگ) |
| **گوشی اندروید arm64**، اندروید ۶ به بالا | بازی فقط arm64 است |
| **adb** (اختیاری ولی خیلی توصیه‌شده) | نصب سریع + گرفتن لاگ کرش |

اگر `adb` نداری، می‌توانی فایل APK را روی گوشی کپی کنی و با فایل‌منیجر نصب کنی.
(ویندوز: [platform-tools](https://developer.android.com/tools/releases/platform-tools) را دانلود و به PATH اضافه کن.)

---

## ۱. ریپو را بگیر

```bash
git clone https://github.com/Abolfazlerahmati/mafiaso-offline.git
cd mafiaso-offline
```

بدون git: در GitHub روی **Code → Download ZIP** بزن، فایل را باز کن و وارد پوشه‌ی `mafiaso-offline-main` شو.

---

## ۲. دو فایل APK اصلی بازی را بگیر

این دو فایل در Git **نیستند** (حق نشر + حجم). سه راه داری — اولی ساده‌ترین است.

### راه A — از تگ `apk-parts` روی GitHub (بدون نیاز به کافه‌بازار)

```bash
git fetch origin refs/tags/apk-parts:refs/tags/apk-parts --force
mkdir -p original
git archive --format=tar refs/tags/apk-parts | tar -x -C original
rm -f original/part-* original/set.tar     # فایل‌های میانی مال workflow هستند
ls -l original
```

باید این دو فایل را ببینی:

```
base.apk        129,977,246 بایت
split_0.apk      27,993,663 بایت
```

> `base.apk` و `split_0.apk` همان دو فایل اصلی‌اند؛ فقط اسم‌شان کوتاه است.
> اسکریپت build هر دو نام (با `arm64` یا بدون آن) را می‌شناسد.

### راه B — از روی گوشی (اگر بازی از کافه‌بازار نصب است)

```bash
adb shell pm path com.paeezanstudio.pesarkhande
# package:/data/app/~~xxxx/…/base.apk
# package:/data/app/~~xxxx/…/split_config.arm64_v8a.apk
adb pull <مسیر-base>   original/base.apk
adb pull <مسیر-split>  original/split_0.apk
```

### راه C — از سایت‌های میرور

APKPure/APKMirror نسخه‌ی **XAPK** دارند. XAPK در واقع ZIP است؛ از داخلش
`base.apk` و `split_config.arm64_v8a.apk` را بیرون بیاور و در `original/` بگذار.
حتماً نسخه **3.4.2** با `versionCode 3420004`.

### بررسی درستی (مهم)

```bash
sha256sum original/*.apk                  # Linux / macOS
certutil -hashfile original\base.apk SHA256   # Windows
```

| فایل | SHA-256 |
|------|---------|
| `base.apk` | `94a9beca7ae0025062bb1f5ed76541e8a7d1df41054cc491b1b9f5325d67643b` |
| `split_0.apk` | `e47f734399c489d92b65270a141603e80eb956fac1a086d6ec1efb2ee4b29370` |

اگر نخواند، نسخه‌ی دیگری گرفته‌ای. نگران نباش: پچ با «جستجوی رشته» انجام می‌شود،
پس اگر نسخه اشتباه باشد build **با خطا متوقف می‌شود** (`literal not found`) و خروجی خراب نمی‌دهد.

---

## ۳. بساز

### لینوکس / macOS / WSL / Git Bash

```bash
chmod +x build.sh build-all.sh
./build-all.sh          # هر پنج واریانت، حدود ۳ دقیقه
```

یا فقط واریانت A:

```bash
./build.sh
```

### ویندوز (بدون WSL)

دو بار روی **`build.cmd`** کلیک کن (فقط واریانت A).
برای هر پنج واریانت در cmd:

```bat
set BRANCH=0x14c00a8=0x14c6498 & set NO_RENAME=1 & set OUT=out-native & call build.cmd
set BRANCH=0x15a1868=0x14c00ac & set WRITE=0x14c00ac=01008052e2031faa87180014 & set OUT=out-battle & call build.cmd
```

### خروجی سالم چه شکلی است؟

```
[deps] ok (cryptography 50.0.2)
[1/4] patching metadata literals
  literal #4451: 'ConnectionScreen' -> 'MainMenu'
[2/4] patching manifest (isSplitRequired -> false)
[3/4] rebuilding APK with 16 native libraries
[4/4] signing
verify: v2 OK
```

و پنج فایل:

```
out/pesarkhande-offline-arm64.apk
out-native/pesarkhande-offline-arm64.apk
out-battle/pesarkhande-offline-arm64.apk
out-debug/pesarkhande-offline-arm64.apk
out-bot/pesarkhande-offline-arm64.apk
```

هر کدام حدود **۱۵۸ مگابایت** و امضای v1/v2/v3 معتبر.

> کلید امضای شخصی در `keys/` ساخته می‌شود. **نگهش دار** — بیلدهای بعدی با همان کلید
> امضا می‌شوند تا روی نسخه‌ی قبلی نصب شوند. اگر پوشه‌ی `keys/` را پاک کنی، باید
> بازی را از گوشی حذف و دوباره نصب کنی.

---

## ۴. روی گوشی نصب کن

۱. گوشی: **تنظیمات → امنیت → نصب از منابع ناشناس** را روشن کن.
۲. اگر بازی اصلی روی گوشی است، **حذفش کن** (امضای ما با Paeezan Studio فرق دارد و
   اندروید نصب روی نسخه‌ی امضاشده را رد می‌کند):
   ```bash
   adb uninstall com.paeezanstudio.pesarkhande
   ```
۳. نصب:
   ```bash
   adb install out-debug/pesarkhande-offline-arm64.apk
   ```
   یا فایل را روی گوشی کپی کن و با فایل‌منیجر نصب کن.

نکته: هر پنج بیلد **روی هم** نصب می‌شوند (پکیج و کلید یکی است)، پس لازم نیست بین
تست‌ها حذف کنی — فقط یکی را در هر لحظه نصب داشته باش.

---

## ۵. تست کن — به این ترتیب

| # | فایل | چه چیزی را ثابت می‌کند | انتظار |
|---|------|------------------------|--------|
| A | `out/…apk` | منو بدون صفحه‌ی اتصال | لوگو → لودینگ → **منوی اصلی** |
| B | `out-native/…apk` | همان A با پچ کد بومی | مثل A (یک لحظه صحنه‌ی اتصال) |
| C | `out-battle/…apk` | ورود به آرنا | منو → دکمه‌ی نبرد → `Arena_1` |
| D | `out-debug/…apk` | GUI دیباگ خودِ بازی | در آرنا، دکمه‌های **Start Battle / Test Draft / Test Random** روی صفحه |
| E | `out-bot/…apk` | نبرد خودکار با بات | منو → نبرد → دو تیم روی زمین → نوبت ۴۰ ثانیه‌ای |

**ترتیب پیشنهادی: A → C → D → E.** هر کدام کار کرد، همان را نگه دار.

### چه چیزی را یادداشت کنی؟

برای هر بیلد فقط این سه خط:

```
بیلد X: منو آمد؟ بله/نه | کرش؟ بله/نه | چه دیدم: …
بیلد C: وارد آرنا شد؟ بله/نه | چه دیدم: …
بیلد D: دکمه‌ی Start Battle را زدم → …
بیلد E: دو تیم آمدند؟ بله/نه | نوبت شروع شد؟ بله/نه
```

همین کافی است تا پچ بعدی دقیق باشد.

### اگر کرش کرد

```bash
python3 tools/diagnose.py            # ۲۵ ثانیه لاگ + مشخصات گوشی → فایل diagnose-*.txt
```

فایل ساخته‌شده را بفرست. اگر `adb` نداری، با Matlog یا Logcat Reader خروجی بگیر و
`python3 tools/diagnose.py --logcat FILE` بده.

---

## ۶. خطاهای رایج

| خطا | معنی | راه‌حل |
|-----|------|--------|
| `!! base APK not found` | فایل در `original/` نیست | دو APK را در `original/` بگذار |
| `literal not found: 'ConnectionScreen'` | نسخه‌ی اشتباه (۳.۴.۲ نیست) | فایل درست را بگیر (هش‌ها را چک کن) |
| `python3: command not found` | Python نصب نیست / در PATH نیست | از python.org نصب کن و «Add to PATH» را بزن |
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | بازی اصلی با کلید دیگری نصب است | `adb uninstall com.paeezanstudio.pesarkhande` |
| `INSTALL_FAILED_NO_MATCHING_ABIS` | گوشی arm64 نیست | این پچ فقط arm64 است |
| `INSTALL_FAILED_MISSING_SPLIT` | بیلد بدون `--single` | از `out*/…apk` (APK تکی) استفاده کن |
| منوی خالی / بدون کارت | پروفایل از سرور می‌آید | طبیعی است؛ بیلد D/E را تست کن و نتیجه را بگو |

---

## ۷. اگر الان گوشی داری نیست

کارهی عجله‌ای نیست:

1. قدم ۱ تا ۳ را انجام بده و مطمئن شو `./build-all.sh` پنج APK سالم می‌دهد.
2. پنج فایل را نگه دار.
3. هر وقت گوشی پیدا شد، قدم ۴ و ۵ — و همان چند خط را بگو.

بیلدها بدون دستگاه هم قابل ساخت و بازبینی‌اند؛ تنها چیزی که دستگاه لازم دارد
«تست واقعی» است.
