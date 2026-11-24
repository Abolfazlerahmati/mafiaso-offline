# زنجیره ابزار — مایل‌ستون M1
## پارسر IL2CPP، بازسازی و امضای APK

> **تاریخ:** 2026-11-24
> **وضعیت:** ✅ ساخته و آزمایش شد (روی فایل‌های واقعی بازی)
> **نیازمندی‌ها:** Python 3.11 + `UnityPy`، `capstone`، `cryptography`، `androguard` + `openssl`

---

## ۱. چرا این ابزارها؟

سندباکس به SDK اندروید و به .NET دسترسی ندارد؛ بنابراین نه `Il2CppDumper`/`Cpp2IL` قابل اجراست، نه `zipalign`/`apksigner`. دو ابزار زیر جای آن‌ها را می‌گیرند:

| ابزار | جایگزینِ | کار |
|-------|----------|-----|
| `tools/il2cpp.py` | Il2CppDumper (بخشی) | پارس `global-metadata.dat` v31 + `libil2cpp.so`، نگاشت کلاس/متد/فیلد → آدرس بومی، دیس‌اسمبل ARM64 |
| `tools/apk.py` | zipalign + apksigner | بازسازی ZIP با ترازبندی، امضای v1+v2+v3، راستی‌آزمایی رمزنگاری |

هر دو فقط با کتابخانه‌های PyPI کار می‌کنند و قابل بازتولید هستند.

---

## ۲. `tools/il2cpp.py`

### ۲.۱. ساختارهای پارس‌شده (metadata v31)

| ساختار | اندازه | تعداد در بازی |
|--------|-------:|--------------:|
| `Il2CppTypeDefinition` | 88 بایت | ۱۶٬۶۲۷ |
| `Il2CppMethodDefinition` | 36 بایت | ۱۱۰٬۳۳۹ |
| `Il2CppFieldDefinition` | 12 بایت | ۷۳٬۳۳۲ |
| `Il2CppImageDefinition` | 40 بایت | ۱۲۸ |
| `Il2CppStringLiteral` | 8 بایت | ۲۳٬۲۷۰ |

### ۲.۲. نکات فنی مهم

- **Relocationها:** در یک shared object، اشاره‌گرهای `.data.rel.ro` به‌صورت ۰ ذخیره می‌شوند و در زمان بارگذاری با `R_AARCH64_RELATIVE` (نوع `0x403`) پر می‌شوند. ابزار ۳۵۸٬۸۱۹ relocation را پارس می‌کند و در هر خواندنِ pointer اعمال می‌کند — بدون این، هیچ `Il2CppCodeGenModule`‌ای پیدا نمی‌شود.
- **بخش `il2cpp`:** کد تولیدشده در بخشی با نام `il2cpp` (نه `.text`) قرار دارد؛ بازه اجرایی `0x10e8380..0x2a5a9dc` است.
- **یافتن ماژول:** رشته‌ی `Assembly-CSharp.dll` در `.rodata` پیدا و سپس اشاره‌گرِ (relocation-شده) به آن در `.data.rel.ro` جست‌وجو می‌شود → `Il2CppCodeGenModule` در `0x2a7b0c0` با ۲۴٬۶۹۶ متد.
- **نگاشت متد → آدرس:** `token & 0xFFFFFF` شماره‌ی ۱-پایه‌ی متد در آرایه‌ی `methodPointers` است.

### ۲.۳. دستورها

```bash
python tools/il2cpp.py info
python tools/il2cpp.py classes Connection
python tools/il2cpp.py class ConnectionManager
python tools/il2cpp.py method SimulateBotAction
python tools/il2cpp.py literal "DEBUG"
python tools/il2cpp.py disasm 0x14c00a8 --count 120
```

### ۲.۴. یافته‌های تأییدشده (خروجی واقعی)

```
=== ConnectionManager  (type #762, token 0x20002f9) ===
fields : infoText, button, inputField, versionText,
         offlineMode, skipTut, fakeBuy, disableSSL,
         ConnectionMenu, m_LanguageMenu, socketComponent, doOnMainThread,
         UniqueID, HID, DeviceID, hintText, supportButton, ...,
         customProfileManager, _canvas, ..., connectionState, isReconnecting
methods (نمونه):
  SetupFlow          0x14c00a8
  TryLogin           0x14c0d54
  OnConnected        0x14c20d4
  OnLoggedIn         0x14c2260
  MT_OnLoggedIn      0x14c3840
  ContinueLogin      0x14c5870
  LoadMainMenu       0x14c6498
  LoadBattle         0x14c62d0
```

```
=== DebugConnectionMenu (type #763) ===
fields : urlInputField, offlineMode, skipTut, fakeBuy, disableSSL,
         connectButton, loadLastButton, loadTestUrlButton
methods: OnEnable 0x14c792c, LoadLastAddress 0x14c7a14,
         LoadTestAddress 0x14c7c78
```

```
=== TesterToolUnlockManager (type #803) ===
fields : _instance, testerToolSwipeDetector, testersRootGameObject,
         testerCounterThreshold, lastClickTime, counter

=== TesterToolSwipeDetector (type #802) ===
fields : topEdgeThreshold, minSwipeDistance, maxHorizontalDrift,
         showDebugLogs, OnSwipeDownFromTop, _startPosition, _isOverUI
methods: Update 0x14cfe58, OnApplicationFocus 0x14d018c
```

> `TesterToolSwipeDetector.Update` ابتدا `Input.touchCount` را می‌خواند، سپس موقعیت لمس و `Screen.height` را مقایسه می‌کند: لمس باید در فاصله‌ی `topEdgeThreshold` از **لبه‌ی بالای صفحه** شروع شود و به سمت پایین کشیده شود. یعنی **«سوایپ از لبه‌ی بالا به پایین»** کلید باز کردن ابزارهای تستری است.

```
=== TesterToolsManager (type #801) ===
testersCustomProfileManager, testerSkinUnlocker, testerRecoverByHID,
testerHeroUnlocker, testerChestAdder, testerJokerOffer, inGameDebugConsole
```

> این یعنی بازی یک **کنسول تستری داخلی** دارد: تنظیم XP/جم/طلا/جام، باز کردن قهرمان، اسکین و صندوق، و کنسول دیباگ.

---

## ۳. `tools/apk.py`

### ۳.۱. امکانات
- `rebuild`: کپی ورودی‌ها با حفظ ترتیب/فشرده‌سازی، جایگزینی/حذف فایل، ترازبندی ۴ بایتی برای ورودی‌های ذخیره‌شده و `resources.arsc`.
- `sign`: امضای **v1 (JAR)** + **v2** + **v3** با کلید RSA خودامضا.
- `verify`: بازخوانی با androguard + **بازمحاسبه‌ی digest و راستی‌آزمایی RSA** (تست پذیرش واقعی).

### ۳.۲. نکات پیاده‌سازی
- ZIP از **raw DEFLATE** استفاده می‌کند (بدون هدر zlib) — استفاده از `zlib.compress` خراب می‌شود.
- پیشوندهای طول *داخل* بلوک امضا **uint32** هستند (نه uint64)؛ فقط اندازه‌ی خود بلوک uint64 است.
- `resources.arsc` باید ذخیره‌شده (بدون فشرده‌سازی) و تراز شده باشد.
- امضای v1 با `openssl smime -sign -binary -noattr` ساخته می‌شود (گواهی داخل PKCS#7).

### ۳.۳. نتیجه‌ی آزمون

```
$ python tools/apk.py rebuild --in base.apk --out rebuilt.apk
$ unzip -t rebuilt.apk      → No errors detected in compressed data

$ python tools/apk.py sign --in rebuilt.apk --out signed.apk ...
$ python tools/apk.py verify --in signed.apk
package          : com.paeezanstudio.pesarkhande
versionName      : 3.4.2
versionCode      : 3420004
signed v1/v2/v3  : True / True / True
v2 crypto check  : True — v2 OK (algo 0x101, subject=O=Personal Build,CN=mafiaso-offline)
```

> **محدودیت:** پارسر v2 خودِ androguard با پیشوندهای طول مشکل دارد (`get_certificates_der_v2` خطا می‌دهد)؛ اما `openssl pkcs7` و `openssl smime -verify` هر دو امضای v1 را تأیید می‌کنند و بازمحاسبه‌ی رمزنگاری v2 در `verify_v2_crypto` موفق است. تأیید نهایی فقط با نصب روی دستگاه ممکن است.

---

## ۴. آزمون M0 — دستور برای کاربر

بازی **نسخه‌ی اصلی 3.4.2** را نصب کنید (بدون هیچ پچی) و این را امتحان کنید:

1. برنامه را باز کنید و به صفحه‌ی اتصال بروید.
2. انگشت را **دقیقاً روی لبه‌ی بالای صفحه** بگذارید و **به سمت پایین بکشید** (مثل باز کردن نوار اعلان‌ها).
3. اگر پنل «ابزارهای تستری» باز شد: گزینه‌های `offlineMode`، `skipTut`، `fakeBuy` را ببینید و نتیجه را گزارش کنید.
4. اگر باز نشد: چند بار پشت‌سرهم روی **متن نسخه** (پایین صفحه) ضربه بزنید (شمارنده‌ی `testerCounterThreshold`).
5. در هر حالت بگویید چه چیزی دیدید — این نتیجه مسیر M2 را تعیین می‌کند.

---

## ۵. گام بعدی (M2 — بوت آفلاین)

1. تعیین دقیق آفست فیلدهای `ConnectionManager` (از کد یا `Il2CppMetadataRegistration`).
2. پیدا کردن محل خواندن `offlineMode` و مسیر `SetupFlow → LoadMainMenu`.
3. پچ حداقلی + بازسازی + امضا + تست روی دستگاه.

---

## ۶. محدودیت‌های فعلی

| مورد | وضعیت |
|------|--------|
| اجرای بازی در سندباکس | ❌ ممکن نیست |
| تست نصب | ❌ فقط روی دستگاه کاربر |
| پارسر v2 androguard | ⚠️ محدودیت خود کتابخانه (نه امضا) |
| فیلد آفست‌ها | ⚠️ از metadata v31 قابل استخراج نیست؛ باید از کد استنباط شود |

---

## ۷. `tools/patch.py` — پچ داده‌محور و بازسازی بسته

### ۷.۱. چرا پچ داده به‌جای پچ باینری؟
Unity صحنه‌ها را **با نام** بارگذاری می‌کند (`SceneManager.LoadScene("ConnectionScreen")`). نام‌ها در جدول `Il2CppStringLiteral` متادیتا ذخیره شده‌اند؛ بنابراین تغییر یک رشته، مسیر بوت را عوض می‌کند **بدون دست زدن به یک بایت از کد IL2CPP**.

### ۷.۲. دستور
```bash
python tools/patch.py build \
  --base original/pesarkhande-3.4.2-base.apk \
  --split original/pesarkhande-3.4.2-split_config.arm64_v8a.apk \
  --rename ConnectionScreen=MainMenu \
  --out out/
```

خروجی: `pesarkhande-offline-base.apk` + `pesarkhande-offline-split_config.arm64_v8a.apk` (هر دو با یک کلید امضا شده‌اند).

نصب:
```bash
adb install-multiple out/pesarkhande-offline-base.apk \
                     out/pesarkhande-offline-split_config.arm64_v8a.apk
```
یا با برنامه‌ی **SAI** (نصب split APK) روی گوشی.

### ۷.۳. نتیجه‌ی آزمون واقعی
```
[1/4] patching metadata literals
  literal #4451: 'ConnectionScreen' -> 'MainMenu'
[2/4] rebuilding base APK
[3/4] signing base
[4/4] rebuilding + signing split

verifying:
  pesarkhande-offline-base.apk: v2 OK
  pesarkhande-offline-split_config.arm64_v8a.apk: v2 OK
```
بازبینی مستقیم متادیتای خروجی: `#4451 = 'MainMenu'` ✓ و هر دو APK با `unzip -t` سالم‌اند.

### ۷.۴. محدودیت‌های پچ
- **`offlineMode` پیدا نشد:** در IL2CPP v31 آفست فیلدها در زمان اجرا محاسبه می‌شود و در متادیتا نیست؛ جدول آفست‌های موجود در `.rodata` هم با ایندکس فیلدهای متادیتا هم‌خوان نبود. هیچ متدی در `ConnectionManager` هم بولی را در آفست‌های طبیعی (0x30..0x33) نمی‌خواند. بنابراین «true کردن offlineMode» بدون تحلیل بیشتر عملی نیست.
- **راه‌جانشین:** تغییر نام صحنه (این پچ) یا **کنسول تستری** (سوایپ از لبه‌ی بالا).
- این پچ فقط **مسیر بوت** را عوض می‌کند؛ پروفایل بازیکن هنوز از سرور می‌آید. اگر منو بدون پروفایل کرش کرد، مرحله‌ی بعدی ساخت پروفایل محلی است.
