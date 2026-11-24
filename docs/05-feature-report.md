# گزارش قابلیت‌ها و محدودیت‌ها — وضعیت تحویل

> **تاریخ:** 2026-11-24
> **قاعده:** هر قابلیتی که بازسازی شده، صریحاً «بازسازی‌شده/تقریبی» علامت می‌خورد.
> ادعای تطابق با سرور اصلی **بدون آزمون** مطرح نشده است.

---

## ۱. وضعیت کلی

| حوزه | وضعیت | توضیح |
|------|-------|-------|
| زنجیره ابزار | ✅ کامل | پارسر IL2CPP، بازسازی ZIP، امضای v1+v2+v3، اسکریپت build برای Linux/macOS/Windows |
| بوت آفلاین (رد شدن از صفحه‌ی اتصال) | 🟡 دو واریانت ساخته‌شده، **آزمون‌نشده** | A: پچ داده‌محور `ConnectionScreen → MainMenu`؛ B: پچ کد بومی `SetupFlow → LoadMainMenu` |
| ادغام base+split در یک APK | ✅ کامل | `isSplitRequired=false`، ۱۶ کتابخانه‌ی بومی |
| پروفایل محلی | ❌ انجام نشده | بازی هنوز پروفایل را از سرور می‌خواهد |
| نبرد آفلاین با AI | 🟡 دو بیلد آزمایشی | `out-battle/` فقط وارد آرنا می‌شود؛ `out-bot/` سه مسیر `PrepareAndWaitForStart*` را به `InitTestMode` وصل می‌کند (spawn هر دو تیم + نوبت ۴۰ ثانیه‌ای) |
| ذخیره‌ی محلی / بکاپ | ❌ انجام نشده | فقط راهنمای `adb backup` |
| فروشگاه شبیه‌سازی‌شده | ❌ انجام نشده | `fakeBuy` در بازی هست ولی در دسترس نیست |
| حذف SDKهای شبکه | ❌ انجام نشده | هنوز در APK هستند |

---

## ۲. جزئیات فنی

### ۲.۱. آنچه ساخته و **آزمایش** شده

| مورد | شواهد |
|------|-------|
| پارس متادیتا v31 | ۱۶٬۶۲۷ نوع / ۱۱۰٬۳۳۹ متد / ۷۳٬۳۳۲ فیلد / ۲۳٬۲۷۰ رشته — همه با نام صحیح |
| حل relocation | ۳۵۸٬۸۱۹ ورودی؛ بدون آن هیچ ماژولی پیدا نمی‌شد |
| نگاشت متد → آدرس | `Assembly-CSharp` با ۲۴٬۶۹۶ متد؛ آدرس‌ها در بازه‌ی `il2cpp` |
| بازسازی ZIP | `unzip -t` بدون خطا؛ `resources.arsc` ذخیره‌شده و تراز شده |
| امضای v1 | `openssl smime -verify` تأیید می‌کند |
| امضای v2/v3 | بازمحاسبه‌ی digest + RSA → `v2 OK` |
| پچ متادیتا | literal #4451 واقعاً `MainMenu` شد |
| پچ AXML | `isSplitRequired="false"` با androguard تأیید شد |
| APK تکی | ۱۵۱ مگابایت، ۷٬۹۵۷ ورودی، ۱۶ کتابخانه، v1/v2/v3 معتبر |
| امضا بدون OpenSSL | مسیر جایگزین با `cryptography`: `openssl smime -verify` روی خروجی → `verification successful`؛ محتوای غیرامضایی با مسیر OpenSSL بایت‌به‌بایت یکسان |
| build از صفر | `build.sh` با venv تازه + `pip install cryptography`: ۲۷ ثانیه |
| دیتابیس ارجاع استاتیک | `tools/xref.py`: ۱۲۵ ماژول، ۲۴٬۶۹۶ متد `Assembly-CSharp`، آفست فیلدها، خواندن/نوشتن هر فیلد، دیس‌اسمبل حاشیه‌نویسی‌شده |
| پچ کد بومی | `b 0x14c6498` در `0x14c00a8`: در APK خروجی دقیقاً یک بلوک ۴KB تغییر کرده و دستور به هدف دیکد می‌شود |
| پچ منیفست | `assets/pesarkhande-offline/patches.json` داخل APK: لیست رشته‌ها/آدرس‌ها/بایت‌های قبل و بعد |

### ۲.۲. آنچه **آزمون نشده** (نیازمند دستگاه)

| مورد | ریسک |
|------|------|
| بالا آمدن منو با واریانت A (`ConnectionScreen→MainMenu`) | متوسط — منو با پروفایل خالی بالا می‌آید |
| بالا آمدن منو با واریانت B (`SetupFlow→LoadMainMenu`) | متوسط — `ConnectionManager` ساخته می‌شود ولی `Init`/`ConnectToServer` اجرا نمی‌شود |
| عدم درخواست شبکه | متوسط — SDKها هنوز فعال‌اند |
| پایداری | نامشخص |
| هر دو واریانت روی هم نصب می‌شوند | ✅ (پکیج و کلید امضا یکی است) |

---

## ۳. چرا بقیه انجام نشد

### ۳.۱. پروفایل محلی
`PlayerProfile` کاملاً استاتیک است (۱۸۰ فیلد) و تنها مسیر پرشدنش
`ConnectionManager.SetProfileData → PlayerProfile.SetPlayerProfile(json)` است که از پاسخ سرور
غذاء می‌گیرد. سه گزینه‌ی آفلاین:

1. **پچ بومی:** در `SetupFlow` به‌جای `LoadMainMenu`، ابتدا یک JSON پیش‌فرض به
   `SetPlayerProfile` بدهیم — نیازمند ساخت `Il2CppString`/`JSONObject` از کد تزریقی است.
2. **پچ داده‌ای:** جایگزینی TextAsset پروفایل با فایل محلی (اگر بازی چنین مسیری داشته باشد).
3. **کنسول تستری:** `TestersCustomProfileManager` فقط InputField پر می‌کند (تأیید شد) و
   state بازی را عوض نمی‌کند — پس به‌تنهایی کافی نیست.

نکته‌ی مثبت: منو با پروفایل خالی لزوماً کرش نمی‌کند — `MenuManager.Start` و
`PopulatePopups` روی فیلدهای استاتیک با مقدار پیش‌فرض کار می‌کنند. تا تست دستگاه،
این ریسک باز است.

### ۳.۲. نبرد آفلاین
`BotController`، `LevelController.InitTestMode`، `SimulateBotAction` و `MenuManager.AskPlayWithBot`
در باینری وجود دارند، اما:
- ورود به نبرد از `MenuManager.StartBattle` (رویداد `startbattle`) → سرور → `MT_OnJoinroom` →
  `ConnectionManager.LoadBattle` می‌گذرد.
- `AskPlayWithBot` فقط یک `PopupMessageManager.ShowMessage` با کلیدهای
  `KEY_NO_PLAYER_FOUND` / `KEY_PLAY_WITH_BOT` نشان می‌دهد؛ اکشن واقعی‌اش در callback است.
- `CustomArena` صحنه‌ی کاملی است ولی `CustomArenaLoader` فقط از `Constants.customArenaID` می‌خواند.

**مسیر M3 (پیاده‌سازی‌شده به‌صورت بیلد آزمایشی):** `ConnectionManager.LoadBattle(int roomID, string customArenaID)`
در `0x14c62d0` قرار دارد، `LoadScene("LoadingScreen")` می‌زند و
`Constants.NextScene = "Arena_" + (roomID+1)` می‌گذارد؛ `x0` (this) را نمی‌خواند.
پس یک کُد کِیو سه‌دستوری در بدنه‌ی مرده‌ی `SetupFlow` + یک `b` در ابتدای
`MenuManager.StartBattle` (`0x15a1868`) ورود به `Arena_1` را بدون سرور ممکن می‌کند
(بیلد سوم در `docs/04-install-guide.md`).

**نامشخص:** داخل `Arena_1`، `LevelController` با `Constants.LiveMode == true` احتمالاً
منتظر رویداد حریف می‌ماند. برای نبرد واقعی باید `BotController` فعال شود
(`LevelController.InitTestMode` / `SimulateBotAction`) — نیازمند مشاهده‌ی لاگ روی دستگاه.

**یافته‌ی مهم (بیلد چهارم):** `LevelController.InitTestMode` (`0x149f16c`) یک شروع‌کننده‌ی
کامل آفلاین است: `SetActive(false)` روی دراپ‌داون/انتخاب آرنا، `SpawnOurUnits`،
`FillEnemyUnitsToSpawn`، `SpawnEnemyUnits`، مدت نوبت = `40.0f` (`0x42200000`)، `PAID = 1`،
و jump به `0x149d780`. در بازی اصلی فقط از دکمه‌ی دیباگ `OnGUI` («Start Battle») صدا
زده می‌شود. بیلد `out-bot/` سه مسیر `PrepareAndWaitForStart*` را به آن وصل می‌کند.
مسیر جایگزین (بدون پچ آرنا): `MenuManager.AskPlayWithBot` → `MT_OnJoinroom(data)` که
خودش `BotController.Init` را صدا می‌زند — ولی به یک `JSONObject` نیاز دارد.

### ۳.۳. `offlineMode` (حل شد)
آفست‌ها با `tools/xref.py layout` به‌دست آمد: `ConnectionManager.offlineMode = 0x40`،
`Constants.OfflineMode = 0x1b0`، `Constants.LiveMode = 0x1a4`، `Constants.isInDevelopment = 0x18c`.

- `Constants.OfflineMode` فقط دو نویسنده دارد: `ConnectToServer` (از `ZPlayerPrefs.lastOfflineToggle`)
  و `..cctor` (هر دو `false`).
- **اما** `MenuManager.TurnMenuListenersOn` در صورت `SocketIOComponent.Instance == null`
  مقدار `true` می‌نویسد → بوت مستقیم به منو، خودبه‌خود بازی را در حالت آفلاین قرار می‌دهد.
- `ConnectionManager.offlineMode` فقط داخل `ConnectToServer` خوانده می‌شود، پس در بوت آفلاین بی‌اثر است.
- `DebugConnectionMenu` هیچ کد نوشتن ندارد (تأیید شد).

---

## ۴. نقشه‌ی ادامه‌ی کار (پیشنهادی)

| اولویت | کار | روش |
|--------|-----|------|
| ۱ | تست T1–T3 روی دستگاه | کاربر |
| ۲ | کنسول تستری (سوایپ از لبه‌ی بالا) | کاربر — اگر باز شود، مسیر کوتاه می‌شود |
| ۳ | تزریق پروفایل محلی | پچ بومی `SetupFlow` → ساخت پروفایل پیش‌فرض → `LoadMainMenu` |
| ۴ | ورود به `CustomArena` بدون سرور | پچ `LoadBattle` |
| ۵ | ذخیره‌ی محلی | جایگزینی `SaveSystem` با فایل JSON |
| ۶ | حذف SDKهای شبکه | حذف کلاس‌ها/بسته‌ها از DEX + manifest |
| ۷ | فروشگاه شبیه‌سازی‌شده | استفاده از `fakeBuy` |

---

## ۵. محدودیت‌های قطعی

1. **بدون دستگاه نمی‌توان نهایی‌سازی کرد** — هر پچ باید روی گوشی آزموده شود.
2. **Unity 6 / IL2CPP v31** — ابزارهای قدیمی سازگار نیستند؛ پارسر اختصاصی نوشته شد.
3. **حقوقی** — منابع بازی متعلق به Paeezan Studio است؛ استفاده فقط شخصی و آفلاین.
4. **شبکه‌ی سندباکس** — فقط GitHub/PyPI؛ APKها باید جداگانه گرفته شوند.

---

## ۶. جمع‌بندی

**تحویل‌شده:** یک زنجیره‌ی ابزار کامل و قابل بازتولید (پارسر، دیتابیس ارجاع استاتیک،
پچ داده‌ای و بومی، بازسازی، امضای v1+v2+v3)؛ **دو** APK تکی ۱۵۱ مگابایتی با دو راهبرد
متفاوت برای بوت آفلاین؛ مستندات ساخت/نصب/عیب‌یابی/گزارش قابلیت‌ها.

**ناتمام:** بازی هنوز آفلاین **قابل بازی** نیست. برای کامل شدن، حلقه‌ی
«پچ → نصب → لاگ → پچ بعدی» باید با حضور دستگاه اجرا شود.
