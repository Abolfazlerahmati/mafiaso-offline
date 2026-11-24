# زنجیره ابزار — مایل‌ستون M1
## پارسر IL2CPP، بازسازی و امضای APK

> **تاریخ:** 2026-11-24
> **وضعیت:** ✅ ساخته و آزمایش شد (روی فایل‌های واقعی بازی)
> **نیازمندی‌ها (تحلیل):** Python 3.11 + `UnityPy`، `capstone`، `cryptography`، `androguard` + `openssl`
> **نیازمندی‌ها (فقط ساخت APK):** Python 3 + `cryptography` + `openssl` — `UnityPy`/`capstone`/`androguard` لازم نیستند

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
- `generate_signing_key` / `ensure_signing_key`: ساخت کلید RSA-2048 + گواهی خودامضای ۱۰ ساله با `cryptography` (بدون نیاز به `openssl`).
- `verify`: بازخوانی با androguard + **بازمحاسبه‌ی digest و راستی‌آزمایی RSA** (تست پذیرش واقعی).

### ۳.۲. نکات پیاده‌سازی
- ZIP از **raw DEFLATE** استفاده می‌کند (بدون هدر zlib) — استفاده از `zlib.compress` خراب می‌شود.
- پیشوندهای طول *داخل* بلوک امضا **uint32** هستند (نه uint64)؛ فقط اندازه‌ی خود بلوک uint64 است.
- `resources.arsc` باید ذخیره‌شده (بدون فشرده‌سازی) و تراز شده باشد.
- امضای v1 یک PKCS#7 `SignedData` بدون attribute امضاشده است: اگر `openssl` روی سیستم باشد با `openssl smime -sign -binary -noattr` ساخته می‌شود؛ در غیر این صورت با `cryptography.hazmat.primitives.serialization.pkcs7.PKCS7SignatureBuilder` (گزینه‌ی `NoAttributes`). هر دو مسیر آزمایش شده‌اند (بخش ۸.۶).

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

1. ✅ تعیین آفست فیلدهای `ConnectionManager` — با `tools/xref.py layout` (بخش ۱۰).
2. ✅ پیدا کردن مسیر `SetupFlow → LoadMainMenu` و محل خواندن/نوشتن `offlineMode`.
3. ✅ پچ حداقلی (دو واریانت: داده و کد بومی) + بازسازی + امضا.
4. ⏳ تست روی دستگاه — تنها گامی که در سندباکس ممکن نیست.

---

## ۶. محدودیت‌های فعلی

| مورد | وضعیت |
|------|--------|
| اجرای بازی در سندباکس | ❌ ممکن نیست |
| تست نصب | ❌ فقط روی دستگاه کاربر |
| پارسر v2 androguard | ⚠️ محدودیت خود کتابخانه (نه امضا) |
| فیلد آفست‌ها | ✅ با `tools/xref.py layout` (استنباط از کد + `Il2CppMetadataRegistration`) |

---

## ۷. `tools/patch.py` — پچ داده‌محور و بازسازی بسته

### ۷.۱. چرا پچ داده به‌جای پچ باینری؟
Unity صحنه‌ها را **با نام** بارگذاری می‌کند (`SceneManager.LoadScene("ConnectionScreen")`). نام‌ها در جدول `Il2CppStringLiteral` متادیتا ذخیره شده‌اند؛ بنابراین تغییر یک رشته، مسیر بوت را عوض می‌کند **بدون دست زدن به یک بایت از کد IL2CPP**.

### ۷.۲. دستور
```bash
./build.sh
```

معادل دستی:

```bash
python tools/patch.py build \
  --base original/pesarkhande-3.4.2-base.apk \
  --split original/pesarkhande-3.4.2-split_config.arm64_v8a.apk \
  --single \
  --rename ConnectionScreen=MainMenu \
  --out out/
```

خروجی: **`out/pesarkhande-offline-arm64.apk`** — یک APK تکی، قابل نصب با `adb install`.

نصب:
```bash
adb install out/pesarkhande-offline-arm64.apk
```

> حالت `--pair` (بدون `--single`) هنوز پشتیبانی می‌شود و خروجی جداگانه‌ی base+split می‌دهد
> (`adb install-multiple` یا برنامه‌ی SAI).

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
- **`offlineMode`** (به‌روزرسانی): آفست‌ها با `tools/xref.py layout` حل شد — `ConnectionManager.offlineMode = 0x40`، `Constants.OfflineMode = 0x1b0`. نتیجه: این فلگ فقط از `ConnectToServer` (خواندن `ZPlayerPrefs.lastOfflineToggle`) و `..cctor` نوشته می‌شود، پس در بوت مستقیم به منو `false` می‌ماند؛ اما خودِ بازی در `MenuManager.TurnMenuListenersOn` مسیر جایگزین دارد: اگر `SocketIOComponent.Instance == null` باشد، `Constants.OfflineMode = true` می‌شود (بخش ۱۰.۴).
- **راه‌جانشین:** تغییر نام صحنه (این پچ) یا **کنسول تستری** (سوایپ از لبه‌ی بالا).
- این پچ فقط **مسیر بوت** را عوض می‌کند؛ پروفایل بازیکن هنوز از سرور می‌آید. اگر منو بدون پروفایل کرش کرد، مرحله‌ی بعدی ساخت پروفایل محلی است.

---

## ۸. `--single` — ادغام base و split در یک APK

### ۸.۱. مسئله
گیمی که به‌صورت `App Bundle` منتشر شده، روی دستگاه به‌شکل چند APK نصب می‌شود:
یک APK پایه که **هیچ کتابخانه‌ی بومی ندارد** و چند split برای هر ABI. Manifest پایه
`android:isSplitRequired="true"` دارد؛ یعنی به‌تنهایی نصب نمی‌شود و نصب تکی با
`INSTALL_FAILED_MISSING_SPLIT` رد می‌شود.

### ۸.۲. راه‌حل
`tools/axml.py` manifest باینری (AXML) را بدون decompile/recompile ویرایش می‌کند:

- پارس chunkها (`RES_XML_TYPE` → `RES_STRING_POOL_TYPE` → `RES_XML_RESOURCE_MAP_TYPE` → `RES_XML_START_ELEMENT_TYPE`)؛
- یافتن `android:isSplitRequired` از طریق resource-map و string pool؛
- فقط **مقدار** attribute (`data` در `Res_value`، نوع `TYPE_INT_BOOLEAN = 0x12`) از `1` به `0` تغییر می‌کند.

بدون بازسازی کل AXML، بنابراین هیچ id یا ایندکسی جابه‌جا نمی‌شود.

سپس `build_single()` در `tools/patch.py`:
1. literalهای متادیتا را پچ می‌کند (مثل حالت pair)؛
2. manifest را با `set_bool_attribute(..., 'isSplitRequired', False)` ویرایش می‌کند؛
3. هر ۱۶ فایل `lib/arm64-v8a/*.so` را از split به base منتقل می‌کند (بدون تغییر، فقط استخراج و افزودن)؛
4. کلیدهای امضا را در `keys/` می‌سازد (اگر نباشند)؛
5. ZIP را از نو می‌سازد (تراز ۴بایتی، `resources.arsc` ذخیره‌شده) و v1+v2+v3 امضا می‌کند.

### ۸.۳. نتیجه‌ی آزمون واقعی
```
[1/4] patching metadata literals
  literal #4451: 'ConnectionScreen' -> 'MainMenu'
[2/4] manifest: isSplitRequired -> false  (hits=1)
[3/4] merging 16 native libraries from split
[4/4] rebuilding + signing
  v2 OK
```
- خروجی: `pesarkhande-offline-arm64.apk`، ۱۵۱ MB، ۷٬۹۵۷ ورودی، ۱۶ کتابخانه‌ی بومی، `libil2cpp.so` و `libunity.so` موجود.
- `unzip -t` بدون خطا؛ androguard: `isSigned v1/v2/v3 = True/True/True`، `package=com.paeezanstudio.pesarkhande`، `versionName=3.4.2`، `versionCode=3420004`، `isSplitRequired=false`.
- زمان ساخت روی این سندباکس: ~۲۴ ثانیه.

### ۸.۴. محدودیت‌های `--single`
- فقط **arm64-v8a**؛ اگر گوشی armv7 باشد، APK نصب نمی‌شود (`INSTALL_FAILED_NO_MATCHING_ABIS`).
- `extractNativeLibs="true"` نگه داشته شده (بازی به‌هرحال از این ویژگی استفاده می‌کند).
- APK تکی از نصب split‌های دیگر (مثل `split_config.xx` زبان یا تراکم پیکسل) بزرگ‌تر است، ولی کاملاً خودکفاست.

### ۸.۵. `tools/axml.py` — مرجع API
```python
import sys; sys.path.insert(0, 'tools')
from axml import get_bool_attribute, set_bool_attribute

data = open('AndroidManifest.xml', 'rb').read()
get_bool_attribute(data, 'application', 'isSplitRequired')                   # -> True / False / None
data2, hits = set_bool_attribute(data, 'application', 'isSplitRequired', False)  # hits = تعداد جایگزینی
```
فقط attributeهای boolean قابل ویرایش‌اند و فقط **مقدار** عوض می‌شود (۱۶ بایت، بدون جابه‌جایی
هیچ ایندکسی). برای string/int باید `Res_value` گسترش یابد (در صورت نیاز در مراحل بعدی).

### ۸.۶. امضا بدون وابستگی به سیستم — Windows-friendly
چون کاربر خودش روی سیستم خودش build می‌کند، دو وابستگی به ابزارهای سیستم حذف شدند:

| مرحله | قبلاً | اکنون |
|-------|-------|-------|
| ساخت کلید | `openssl req -x509 …` (اجباری) | `apk.generate_signing_key()` با `cryptography` — PKCS#8 + گواهی خودامضا |
| امضای v1 (PKCS#7) | `openssl smime -sign` (اجباری) | `openssl` اگر باشد؛ وگرنه `PKCS7SignatureBuilder` با `NoAttributes` |
| امضای v2/v3 | `cryptography` | بدون تغییر |

تنها وابستگی build: `pip install cryptography` (`requirements.txt`، نسخه‌ی ≥ ۴۱ به‌خاطر `pkcs7`).
`build.sh` (Linux/macOS/WSL/Git Bash) و `build.cmd` (Windows) هر دو محیط مجازی می‌سازند.

**آزمون (سندباکس، ۲۰۲۶-۱۱-۲۴):** دو build جدا با کلیدهای تازه:
- مسیر `openssl`: v2 OK؛ `openssl smime -verify` روی `META-INF/CERT.RSA` → `verification successful`.
- مسیر جایگزین (`MAFIASO_NO_OPENSSL=1`): v2 OK؛ همان oracle → `verification successful`؛ androguard v1/v2/v3 = True.
- محتوای غیرامضایی (همه‌ی ورودی‌های غیر `META-INF/`) در دو build **بایت‌به‌بایت یکسان**.
- `build.sh` با محیط مجازی از صفر (شامل `pip install`): ۲۷ ثانیه، خروجی ۱۵۷٬۹۶۵٬۷۵۳ بایت، v1 تأیید، v2 OK.

> متغیر محیطی `MAFIASO_NO_OPENSSL=1` فقط برای آزمون مسیر جایگزین است؛ کاربر به آن نیازی ندارد.

---

## ۹. `tools/diagnose.py` — گزارش خودکار از دستگاه
چون هر پچ فقط روی گوشی قابل تأیید است، حلقه‌ی «نصب → کرش → لاگ» باید ارزان باشد.
این اسکریپت (فقط stdlib + `adb`):

1. `adb devices` → انتخاب دستگاه؛ `getprop` + `dumpsys package` → مدل، اندروید، ABI، versionCode نصب‌شده؛
2. `adb logcat -c`، اجرای بازی با `monkey -p … -c LAUNCHER 1`، ضبط `-v threadtime` به مدت `--seconds`؛
3. پارس خطوط، طبقه‌بندی: کرش Java/بومی (`FATAL EXCEPTION`, `Fatal signal`, `SIGSEGV`) با **پنجره‌ی ۴۵ خط** برای stack trace،
   `NullReferenceException`، پیام‌های صحنه، تلاش‌های شبکه (دامنه‌های بازی/SDKها)؛
4. نوشتن `diagnose-<timestamp>.txt` با `[device] [summary] [verdict] [crashes] … [filtered log]`.

حالت بدون گوشی: `--logcat FILE` برای تحلیل یک dump موجود. آزمون با logcat ساختگی (NRE در
`MainMenu.Awake`، SIGSEGV با backtrace، `FATAL EXCEPTION`، پیام صحنه، خطای شبکه): هر ۵ دسته شناسایی شد.

---

## ۱۰. `tools/xref.py` — دیتابیس ارجاع استاتیک + دیس‌اسمبل حاشیه‌نویسی‌شده

`il2cpp.py` می‌گوید «چه چیزی در متادیتا هست»؛ `xref.py` می‌گوید «چه چیزی چه چیزی را
صدا می‌زند/می‌خواند». برای پچ کردن بدون سورس، این است که مسیر را قابل استدلال می‌کند.

### ۱۰.۱. اجزا

| جزء | کار |
|------|-----|
| `Registration` | پیدا کردن `Il2CppMetadataRegistration` با اسکن (شرط: `typesCount == fieldOffsetsCount`)؛ در این بیلد در `0x2ad1528` |
| `Modules` | پیمایش آرایه‌ی `Il2CppCodeGenModule`ها → نگاشت «آدرس → متد» + اندازه‌ی هر متد؛ ۱۲۵ ماژول، `Assembly-CSharp` با ۲۴٬۶۹۶ متد از `0x2c80788` |
| `Layout` | آفست فیلدهای **استاتیک و اینستنس** هر نوع، استنباط‌شده از خودِ کد (`str/ldr` روی `static_fields` و `this`) + ثبت‌های metadata |
| `Xref` | دیکد هندل‌های metadata-usage (`(kind<<29)\|(index<<1)\|1`)، اسکن GOT slotها، هدف‌های `bl`، عملوندهای حافظه، و برچسب‌گذاری **خواندن/نوشتن** هر فیلد |
| کش | `work/xref-<module>.pkl`؛ ساخت مجدد < ۱ ثانیه |

### ۱۰.۲. دستورها

```bash
python tools/xref.py layout ConnectionManager          # آفست فیلدها
python tools/xref.py method ConnectionManager SetupFlow # امضا + آدرس + اندازه
python tools/xref.py disasm ConnectionManager LoadMainMenu
python tools/xref.py type PlayerProfile [--no-mem]
python tools/xref.py callers ConnectionManager.LoadMainMenu
python tools/xref.py uses --field Constants.OfflineMode [--writes]
python tools/xref.py uses --literal ConnectionScreen
python tools/xref.py uses --call SceneManager.LoadScene
python tools/xref.py find "Swipe"
```

### ۱۰.۳. نمونه‌ی خروجی واقعی

```
$ python tools/xref.py uses --field Constants.OfflineMode
  MenuManager.TurnMenuListenersOn @ 0x159ba1c  [w]
  ConnectionManager.ConnectToServer @ 0x14c1b5c  [w]
  SaveSystem.GetInt @ 0x172e910  [r]
  ...

$ python tools/xref.py disasm ConnectionManager LoadMainMenu
  0x0014c6518  ldr  x0, [x21]      ; load 'LoadingScreen'
  0x0014c651c  bl   #0x270ff70     ; UnityEngine.SceneManagement.SceneManager.LoadScene
  0x0014c6530  ldr  x0, [x19]      ; load 'MainMenu'
  0x0014c6540  b    #0x170b124     ; Constants.set_NextScene
```

برچسب فیلدها در دیس‌اسمبل از `Layout` می‌آید؛ بدون آن، آفست‌ها ۸ بایت شیفت نشان داده
می‌شدند (باگ واقعی که در این نسخه رفع شد: `offlineMode` به‌جای `fakeBuy` چاپ می‌شد).

### ۱۰.۴. یافته‌های کلیدی که با این ابزار به‌دست آمد

- **`LoadMainMenu`** = `LoadScene("LoadingScreen")` سپس `Constants.NextScene = "MainMenu"`؛
  `LoadingScreen.LoadLevel` هم `LoadSceneAsync(Constants.NextScene)` را صدا می‌زند
  → پچ رشته‌ی `ConnectionScreen→MainMenu` دقیقاً روی همین مسیر اثر می‌گذارد.
- **`MenuManager.Awake`** همیشه `Constants.LiveMode = true` می‌کند و `TurnMenuListenersOn` را صدا می‌زند.
- **`MenuManager.TurnMenuListenersOn`** ~۱۵ رویداد Socket.IO را register می‌کند؛ اگر
  `SocketIOComponent.Instance == null` باشد، به‌جای آن **`Constants.OfflineMode = true`** می‌نویسد
  (آدرس `0x159c400`). یعنی «منو بدون سوکت» حالتی است که خودِ بازی پیش‌بینی کرده است.
- **`Constants.OfflineMode`** فقط دو نویسنده دارد: `ConnectToServer` و `..cctor` (هر دو `false`).
  خواننده‌ها: `SaveSystem.*`، `InformationAsset.LoadArenas`، `DraftModeManager/RandomModeManager.Update`،
  `MenuManager.CancelBattle`، `PiggyBankV2ButtonHandler`، `Constants.get_isTutorial`.
- **`PlayerProfile`** همه‌اش استاتیک است (۱۸۰ فیلد، صفر اینستنس) و فقط از
  `ConnectionManager.SetProfileData → PlayerProfile.SetPlayerProfile(json)` پر می‌شود
  → در بوت آفلاین، منو با پروفایل خالی (`..cctor`) بالا می‌آید. این مهم‌ترین ریسک باقی‌مانده است.
- **شروع‌کننده‌ی نبرد آفلاین:** `LevelController.InitTestMode` در `0x149f16c` —
  `SpawnOurUnits` + `FillEnemyUnitsToSpawn` + `SpawnEnemyUnits`، مدت نوبت `40.0f`،
  `PAID = 1`، سپس jump به `0x149d780`. در بازی اصلی فقط از دکمه‌ی دیباگ `OnGUI` صدا
  زده می‌شود؛ مسیر عادی `PrepareAndWaitForStart*` فقط `Invoke("GameStartTimeOut", t)` است.
- **مسیر بات خودِ بازی:** `MenuManager.AskPlayWithBot` → callback `<>c__DisplayClass253_0.<AskPlayWithBot>b__0`
  → `MenuManager.MT_OnJoinroom(data)`؛ همان متد `PlayerProfile.SetDeck`، `LoadScene`،
  `Constants.set_NextScene` و **`BotController.Init`** را صدا می‌زند.
- **ابزار تستری**: `TesterToolUnlockManager`, `TesterToolSwipeDetector`, `TesterToolsManager`,
  `TesterHeroUnlocker`, `TesterChestAdder`, `TesterSkinUnlocker`, `TestersCustomProfileManager` —
  سوایپ از لبه‌ی بالا در صحنه‌ی اتصال (M0).

### ۱۰.۵. `--branch` — پچ کد بومی (AArch64) در `patch.py`

برای زمانی که پچ داده کافی نیست:

```bash
python tools/patch.py build --base … --split … --single \
  --branch 0x14c00a8=0x14c6498 --out out-native/
```

پیاده‌سازی: سگمنت‌های `PT_LOAD` از هدر ELF خوانده می‌شود (`vaddr → file offset`)، دستور
`b`/`bl` با برد ±۱۲۸ مگابایت encode می‌شود، بایت‌های اصلی قبل از نوشتن چک می‌شوند، و
دستور نوشته‌شده دوباره decode می‌شود تا هدف تأیید شود. نتیجه در
`assets/pesarkhande-offline/patches.json` داخل خودِ APK ثبت می‌شود:

```json
{ "site": "0x14c00a8", "target": "0x14c6498",
  "before": "ffc303d1", "after": "fc180014", "instruction": "b" }
```

راستی‌آزمایی روی خروجی واقعی: در `out-native/…apk` دقیقاً **یک** بلوک ۴ کیلوبایتی از
`libil2cpp.so` با نسخه‌ی اصلی فرق دارد و بایت‌های `0x14c00a8` به `b 0x14c6498` دیکد می‌شوند.

### ۱۰.۶. `--write` — نوشتن بایت خام (کُد کِیو)

برای وقتی که یک `b` تنها کافی نیست و باید آرگومان ساخته شود:

```bash
--write "0x14c00ac=01008052e2031faa87180014"
```

بایت‌ها در همان آدرس مجازی نوشته و بایت‌های اصلی در منیفست ثبت می‌شوند. کاربرد
همزمان با `--branch`: قلاب در ابتدای یک متد + چند دستور در یک ناحیه‌ی مرده‌ی کد.
مثال واقعی (بیلد سوم، بخش «نبرد آزمایشی» در راهنمای نصب):

```
0x15a1868  b    #0x14c00ac        ; MenuManager.StartBattle -> cave
0x14c00ac  mov  w1, #0            ; roomID = 0
0x14c00b0  mov  x2, xzr           ; customArenaID = null
0x14c00b4  b    #0x14c62d0        ; ConnectionManager.LoadBattle
```

`LoadBattle(int roomID, string customArenaID)` خودش `LoadScene("LoadingScreen")` می‌زند و
`Constants.NextScene` را روی `"Arena_" + (roomID + 1)` می‌گذارد؛ `x0` (this) را نمی‌خواند،
بنابراین همین چهار دستور برای ورود به `Arena_1` کافی است.
