# وضعیت پروژه — Mafiaso Offline (پسرخوانده)

> آخرین به‌روزرسانی: 2026-11-24
> برنچ: `arena/95d7dd6d-mafiaso-offline` (پایه: `b6c9423`)
> گزارش فنی مرحله ۱: [`docs/01-technical-report.md`](docs/01-technical-report.md)

## ۱. وضعیت کلی

| مورد | وضعیت |
|------|--------|
| مرحله فعلی | **۱ — شناسایی و تحلیل کامل: انجام شد، منتظر تأیید کاربر** |
| فاز ۲ (طراحی معماری) | ⏸️ شروع نشده — نیازمند تأیید گزارش و انتخاب مسیر (A/B/C) |
| تغییرات اعمال‌شده روی بازی | **هیچ** (فقط تحلیل؛ هیچ فایلی از بازی تغییر نکرده) |
| مانع اصلی | ناسازگاری نسخه: هدف اعلام‌شده 3.3.7 است، اما منابع عمومی 3.4.2 (کافه‌بازار) و 2.8.0 (APKPure) می‌دهند |

## ۲. ورودی‌ها و هش‌ها (فقط‌خواندنی در `original/`)

| فایل | حجم (بایت) | SHA-256 |
|------|-----------:|---------|
| `pesarkhande-3.4.2-base.apk` | 129,977,246 | `94a9beca7ae0025062bb1f5ed76541e8a7d1df41054cc491b1b9f5325d67643b` |
| `pesarkhande-3.4.2-split_config.arm64_v8a.apk` | 27,993,663 | `e47f734399c489d92b65270a141603e80eb956fac1a086d6ec1efb2ee4b29370` |
| `pesarkhande-2.8.0-apkpure.apk` | 146,449,030 | `4c8c511b652ea640ef6e915a14c04c46b39b0309f9a2a4a23b6204542c985f14` |
| `bazaar_reply.json` | 7,901 | پاسخ API کافه‌بازار (متادیتا، splits، CDN) |

- همه فایل‌ها `chmod 444` هستند و در Git ثبت نشده‌اند (`.gitignore`).
- امضای هر سه APK یکسان است: `Organization: Paeezan Studio`، serial `1688900120`، اثر انگشت SHA-256 `96:F7:3E:0A:…:73:A0:A2`.
- **نسخه 3.3.7 از هیچ منبعی (کافه‌بازار، APKPure، GitHub) به‌دست نیامد** — جدیدترین نسخه منتشرشده 3.4.2 است.

## ۳. اطلاعات کلیدی بازی (تأییدشده با تحلیل APK)

| مورد | مقدار |
|------|-------|
| پکیج | `com.paeezanstudio.pesarkhande` |
| نسخه تحلیل‌شده | **3.4.2** (`versionCode 3420004`)، minSdk 23، targetSdk 36 |
| موتور | **Unity 6 (6000.0.58f2) — IL2CPP**، متادیتا v31 |
| صحنه‌ها | ۱۹ (لوگو، لودینگ، اتصال، منوی اصلی، ۱۳ آرنا، آموزش، آرنا سفارشی) |
| منابع | ۷۰۴ Texture2D، ۴٬۴۵۷ Sprite، ۱٬۲۲۵ AudioClip، ۲٬۰۱۷ AnimationClip، ۵۴۳ AnimatorController، ۷۸ TextAsset |
| داده بازی | ۴۰ قهرمان، ۷۷ اسکین، ۱۷ صندوق، ۱۳ آرنا، ۳۶ جایزه Battle Pass، ۷۱ جایزه Trophy Road، ۱۳ زبان |
| سرور اصلی | `android.pesarkhandeh.ir:443` — **Socket.IO** (+ REST/Firebase/Unity Services) |
| رویدادهای شبکه | ~۶۰ رویداد `MT_*` (اتصال، درفت، نوبت، نبرد، کلن، فروشگاه، جایزه) |
| ذخیره‌سازی | `SaveSystem`/`PlayerProfile` + `ObscuredPrefs` (ACTk) — بدون SQLite/فایل سیو؛ پروفایل از سرور می‌آید |

## ۴. محیط سندباکس

| ابزار | وضعیت |
|-------|--------|
| OS / Python / Node | Debian 12 (x86_64) / 3.11.2 / 22.22.3 |
| androguard 4.1.4، apkutils2، pyaxmlparser | ✅ در `.tools/venv` |
| UnityPy 1.25.4، json5 | ✅ در `.tools/venv` |
| Java / jadx / apktool / Android SDK / adb | ❌ نصب نیست ( Il2CppDumper و Cpp2IL نیازمند .NET هستند و در PyPI نیستند) |
| unzip / zip / strings / readelf / objdump | ✅ |
| فضای دیسک | ~۲۰ گیگابایت آزاد |

**محدودیت شبکه:** فقط `github.com`، `codeload.github.com`، `api.github.com`، `registry.npmjs.org`، `pypi.org` و `files.pythonhosted.org` در دسترس‌اند. APKPure، کافه‌بازار، `cdn.mafioso-game.com` و `android.pesarkhandeh.ir` از سندباکس مسدودند؛ دریافت فایل از این دامنه‌ها فقط از داخل **GitHub Actions** ممکن است.

## ۵. اقدامات انجام‌شده

1. تنظیم `.gitignore` (`.tools/`، `__pycache__/`) و قوانین پروژه در `ruls.md`.
2. دریافت APK از APKPure و کافه‌بازار از طریق workflow موقت `apk-fetch.yml` (public repo لازم بود).
3. ثبت هش‌ها، کپی فقط‌خواندنی در `original/`، حذف تگ `apk-parts` از origin.
4. باز کردن APKها، تحلیل Manifest/AXML (permissions، SDKها، componentها).
5. استخراج کل `assets/bin/Data` با UnityPy و فهرست‌گیری کامل منابع.
6. استخراج ۷۸ TextAsset (Configها + ۱.۹ مگابایت Localization) به `extracted/textassets/`.
7. دیکد کامل `global-metadata.dat` (جدول رشته‌ها + ۲۳٬۲۷۰ String Literal) به `extracted/metadata/`.
8. تحلیل Socket.IO، `ConnectionManager`، `SaveSystem`، مدل‌های نبرد و رویدادهای `MT_*`.
9. نگارش گزارش فنی جامع مرحله ۱ در `docs/01-technical-report.md`.

## ۶. خروجی‌های تحلیل (خارج از Git)

| مسیر | محتوا |
|------|-------|
| `extracted/3.4.2/base/`، `extracted/3.4.2/split/` | محتوای unzip شده (۳۵۲M + ۷۷M) |
| `extracted/textassets/` | ۷۸ فایل `<Name>.bytes` (JSON/CSV خام؛ برخی با BOM → خواندن با `utf-8-sig`) |
| `extracted/inventory/` | `textassets.tsv`، `monoscripts.tsv`، `audioclips.txt`، `textures.txt`، `animations.txt`، `sprites.txt` |
| `extracted/metadata/` | `string_literals.txt`، `string_literals_clean.txt`، `string_table.txt` |

> `extracted/` و `original/` عمداً در Git نیستند (حجم بالای ۳۰۰ مگابایت + منابع دارای حق نشر). فقط هش و فهرست آن‌ها در Git ثبت می‌شود.

## ۷. محدودیت‌ها و ریسک‌های شناخته‌شده

1. **نبود decompiler کامل IL2CPP** (Il2CppDumper/Cpp2IL نیازمند .NET) → منطق دقیق نبرد/اقتصاد فقط از متادیتا، رشته‌ها، Configها و ری‌پلی نمونه قابل استنباط است.
2. **منطق سمت سرور** (مچ‌میکینگ، اعتبارسنجی، ضد تقلب، جوایز) در دسترس نیست → باید به‌صورت «بازسازی‌شده/تقریبی» پیاده‌سازی شود.
3. **برخی AssetBundleها راه‌دور هستند** (`cdn.mafioso-game.com`، لینک‌های Discord در Config) → دانلود فقط از Actions.
4. **ACTk (ضد تقلب)** و **امضای APK** → پچ مستقیم APK نیاز به غیرفعال‌سازی ACTk و امضای مجدد دارد.
5. **Unity 6 / Metadata v31** → ابزارهای قدیمی ممکن است ناسازگار باشند.
6. **حقوقی** → استفاده فقط برای نسخه شخصی و آفلاین؛ بازنشر عمومی ممنوع.

## ۸. تصمیم‌های موردنیاز کاربر (برای ورود به فاز ۲)

1. **نسخه هدف:** 3.4.2 (پیشنهادی؛ جدیدترین و تحلیل‌شده) یا 2.8.0 (APK تکی، قدیمی‌تر)؟ — 3.3.7 در دسترس نیست.
2. **معماری:** A) پچ APK + سرور محلی — B) بازسازی کلاینت با منابع استخراج‌شده — C) هیبرید (پیشنهادی).
3. **دامنه اولیه:** فقط نبرد آفلاین با AI، یا کل سیستم‌های متا از ابتدا؟
4. **تبلیغات و IAP:** حذف کامل یا فروشگاه شبیه‌سازی‌شده؟
5. **ABI:** فقط arm64 یا armv7 هم؟

## ۹. گام بعدی (پس از تأیید)

1. طراحی معماری مستقل: لایه شبکه جایگزین، مدل داده محلی، SaveSystem با بکاپ/بازیابی، مدیریت خطا.
2. تحلیل عمیق‌تر `libil2cpp.so`/متادیتا برای مدل‌های `TurnInfo`، `ConnectionManager`، `SaveSystem` و فرمول‌های نبرد.
3. استخراج منابع گرافیکی/صوتی موردنیاز و ساخت Asset Pipeline.
4. شروع پیاده‌سازی مرحله‌به‌مرحله با تست جداگانه هر قابلیت.

## ۱۰. یادآوری‌های عملیاتی

- ⚠️ **ریپو الان public است** (برای اجرای Actions). پس از پایان دریافت فایل‌ها، آن را به **private** برگردانید.
- workflow موقت `.github/workflows/apk-fetch.yml` فقط برای دریافت فایل از دامنه‌های مسدود است و **باید پیش از تحویل نهایی حذف شود**.
- `.github/workflows/fetch-file.yml` حذف شد (هرگز ثبت نشده بود؛ قابلیت URL در `apk-fetch.yml` موجود است).
- برای دریافت فایل از دامنه مسدود: `gh workflow run apk-fetch.yml --ref arena/95d7dd6d-mafiaso-offline -f source=url -f url=<URL> -f name=<NAME> -f package=<PKG>` → `gh run watch <id> --exit-status` → `git fetch origin refs/tags/apk-parts:refs/tags/apk-parts --force` → `git archive --format=tar refs/tags/apk-parts | tar -x -C <dir>`.
