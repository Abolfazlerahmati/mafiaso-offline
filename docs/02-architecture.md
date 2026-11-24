# معماری نسخه آفلاین — مرحله ۲ (طراحی)
## بازی «پسرخوانده / Mafioso» — نسخه 3.4.2

> **تاریخ:** 2026-11-24
> **وضعیت:** پیش‌نویس برای تأیید — **هیچ پیاده‌سازی‌ای انجام نشده است**
> **مبنای طراحی:** `docs/01-technical-report.md` + یافته‌های جدید این سند
> **تصمیم‌های کاربر:** نسخه ۳.۴.۲ · معماری **C (هیبرید)** · دامنه اولیه **نبرد آفلاین با AI** · فروشگاه شبیه‌سازی‌شده · فقط **arm64-v8a**

---

## ۰. خلاصه اجرایی

نسخه آفلاین با **حفظ باینری بازی اصلی** ساخته می‌شود: موتور Unity، صحنه‌ها، UI، انیمیشن‌ها، صداها و منطق سمت کلاینت **دست‌نخورده** می‌مانند و فقط لایه‌هایی که به سرور وابسته‌اند جایگزین می‌شوند. سه لایه جایگزین می‌شوند:

1. **لایه اتصال** → حذف کامل Socket.IO و ورود آنلاین؛ ورود محلی.
2. **لایه داده/ذخیره‌سازی** → پروفایل محلی با فایل JSON + بکاپ/بازیابی.
3. **لایه حریف** → موتور نبرد محلی با `BotController` موجود در بازی.

**کشف کلیدی این مرحله:** بازی خودش یک **حالت آفلاین/تستری داخلی** دارد (`offlineMode`، `skipTut`، `fakeBuy`، `disableSSL`، `ENABLE_DEBUG_MODE`، `DEBUG MODE INFO ►`، `TestersCustomProfileManager`، `InitTestMode`، `SimulateBotAction`). یعنی لازم نیست موتور نبرد را از صفر بنویسیم — باید **مسیر تستری داخلی را فعال و پایدار کنیم**.

---

## ۱. اهداف و غیراهداف

### اهداف
- اجرای کامل بازی **بدون هیچ درخواست شبکه** (تست هواپیما).
- حفظ حداکثری UI، صحنه‌ها، انیمیشن، صدا، کارت‌ها و قهرمانان اصلی.
- نبرد ۳v۳ نوبتی در برابر هوش مصنوعی با قواعد اصلی (۱۵ نوبت، ۴۰ ثانیه، انرژی، مانا/خشم).
- پیشرفت دائمی و قابل بکاپ (پروفایل، قهرمانان، کارت‌ها، صندوق‌ها، جام).
- فروشگاه شبیه‌سازی‌شده با ارز درون‌بازی (بدون پرداخت واقعی).
- نصب آسان: **یک APK** arm64.

### غیراهداف (در این فاز)
- PvP آنلاین، کلن واقعی، چت، لیدربورد سرور.
- دور زدن پرداخت یا دسترسی به حساب/سرور اصلی.
- بازنشر عمومی منابع بازی.

---

## ۲. معماری کلی

```
┌──────────────────────────────────────────────────────────────┐
│  لایه UI / صحنه‌ها (دست‌نخورده)                                │
│  MainMenu · Arena_1..13 · CustomArena · LoadingScreen         │
├──────────────────────────────────────────────────────────────┤
│  لایه منطق بازی (دست‌نخورده)                                   │
│  LevelController · PlayerController · TurnInfo · Actor        │
│  DraftModeManager · BotController · Card/Hero                 │
├──────────────────────────────┬───────────────────────────────┤
│  لایه سرویس محلی (جدید)       │  لایه شبکه (حذف‌شده)            │
│  LocalProfileStore            │  Socket.IO · REST · Firebase   │
│  LocalSaveService             │  Ads · IAP · Analytics         │
│  LocalBattleProvider          │  Unity Services                │
│  LocalShopService             │                                │
│  LocalEventService            │                                │
├──────────────────────────────┴───────────────────────────────┤
│  پلتفرم: Unity 6 / IL2CPP (arm64) + Android                   │
└──────────────────────────────────────────────────────────────┘
```

### اصل طراحی
**«حداقل پچ، حداکثر بازیابی»** — به‌جای بازنویسی، نقاط تکیه‌گاه (choke points) موجود پچ می‌شوند:
- ورود → `ConnectionScreen.SetupFlow` / `offlineMode`
- شروع نبرد → `ConnectionManager.LoadBattle` / `AskPlayWithBot`
- بارگذاری پروفایل → `SaveSystem.LoadProfile`
- ذخیره پروفایل → `SaveSystem.SaveProfile`
- خرید/جایزه → `InAppPurchase` / `RewardSystem`

---

## ۳. یافته‌های جدید (پشتوانه طراحی)

### ۳.۱ حالت آفلاین/تستری داخلی
از `global-metadata.dat` (جدول نام‌ها، به‌ترتیب تعریف نوع‌ها):

| شواهد | معنی |
|-------|------|
| `ConnectionScreen.offlineMode` | فلگ بولی حالت آفلاین روی صفحه اتصال |
| `ConnectionScreen.skipTut` | رد کردن آموزش |
| `ConnectionScreen.fakeBuy` | خرید شبیه‌ای (همان فروشگاه شبیه‌سازی‌شده!) |
| `ConnectionScreen.disableSSL` | غیرفعال کردن SSL (ابزار تست) |
| `ConnectionScreen.versionText` | برچسب نسخه — **محتمل‌ترین تریگر پنهان منوی دیباگ** |
| `ConnectionScreen.customProfileManager` | نمونه `TestersCustomProfileManager` → پروفایل تستری |
| رشته `DEBUG MODE INFO ► ` | برچسب UI منوی دیباگ |
| رشته `ENABLE_DEBUG_MODE` | کلید احتمالی PlayerPrefs/تنظیم |
| `LevelController.InitTestMode` | ورود به حالت تست نبرد |
| `LevelController.SimulateBotAction` | شبیه‌سازی اکشن حریف به‌صورت محلی |
| `LevelController.TestDraft`، `TestEnemyDraft`، `TestDeathDraft`، `TestRandomDraft`، `TestRandom` | سناریوهای تست آماده |
| `BotController.MainRoutine`، `StartTurn`، `GetTurnDuration`، `difficulty`، `CalcHeroLevel`، `GetAllEnemyPossibleActions` | هوش مصنوعی حریف سمت کلاینت |
| `ConnectionManager.AskPlayWithBot` / `CancelPlayWithBot` | پیشنهاد «بازی با ربات» هنگام نبود حریف |

> **نتیجه:** موتور نبرد آفلاین از قبل وجود دارد. کار ما **فعال‌سازی و پایدارسازی** آن است، نه بازنویسی.

### ۳.۲ ترکیب صحنه `CustomArena` (level18)
اسکریپت‌های غیر-UI موجود در صحنه: `CustomArenaLoader`، `LevelController`، `PlayerController`، `SSPlayer`، `TurnInfo`، `DraftModeManager`، `RandomModeManager`، `EndGamePanel`، `ReplayPanel`، `AbilityButtonController`، `ManabarController`، `RageBarController`، `CameraController`، `EnemyRageInfo`، `TurnInfo` → **یک صحنه نبرد کامل و خودکفا**.

### ۳.۳ جریان بوت فعلی (هاردکد در کد)
`Paeezan_MotionLogo` (level0، اسکریپت `PaeezanSplashHandler`) → `LoadingScreen` (level1، اسکریپت `LoadingScreen`) → `ConnectionScreen` (level2) → `MainMenu` (level3).
- بررسی داده سریال‌شده: `PaeezanSplashHandler` فقط یک ارجاع به آبجکت دارد (بدون فیلد شماره صحنه) → **تغییر مسیر بوت نیازمند پچ کد است**.

### ۳.۴ ابزار و محدودیت سندباکس
| نیاز | وضعیت |
|------|--------|
| ویرایش فایل داخل APK | ✅ Python (`zipfile`) |
| بازنویسی `libil2cpp.so` | ✅ Python (`capstone`/`keystone` از PyPI) |
| امضای APK | ⚠️ `pyapksigner`/`apk-signer` فقط wrapper اندروید-SDK هستند → **پیاده‌سازی v1+v2+v3 در Python** (با `cryptography`) |
| `zipalign` | ⚠️ روی PyPI نیست → پیاده‌سازی در Python (ترازبندی ۴ بایتی + `resources.arsc` بدون فشرده‌سازی) |
| اجرای بازی/امولاتور | ❌ **ممکن نیست** → تست فقط روی دستگاه کاربر |
| ساخت کلاینت جدید (Unity/Godot/Flutter) | ❌ **ممکن نیست** (ادیتور/SDK در دسترس نیست) → همین موضوع گزینه B را عملاً منتفی می‌کند |

---

## ۴. مؤلفه‌های معماری

### ۴.۱ `LocalProfileStore` (ذخیره‌سازی)
- **قالب:** یک فایل JSON با نسخه اسکیما (`schemaVersion`) در `Application.persistentDataPath` (یا PlayerPrefs در صورت نیاز به سازگاری با ACTk).
- **محتوا:** همان مدل `PlayerProfile` بازی (طلا، جم، جام، XP، دک، قهرمانان، اسکین‌ها، صندوق‌ها، مأموریت‌ها، Battle Pass، آرنا، تنظیمات).
- **اعتبارسنجی:** هنگام بارگذاری، فیلدهای ناقص با مقدار پیش‌فرض پر می‌شوند (مقاوم در برابر تغییر نسخه).
- **بکاپ:** کپی خودکار قبل از هر نوشتن → `backup/profile-YYYYMMDD-HHMMSS.json` (حداکثر ۱۰ نسخه، چرخشی).
- **بازیابی:** منوی «بازگردانی بکاپ» در تنظیمات + بازیابی خودکار در صورت خرابی فایل اصلی.
- **امنیت محلی:** بدون کلید خصوصی روی دستگاه؛ فایل فقط داده بازی است (نه اطلاعات شخصی).

### ۴.۲ `LocalSaveService`
- جایگزین `SaveSystem.SaveProfile`/`LoadProfile` و `ObscuredPrefs`.
- همه نوشتن‌ها **atomic** (نوشتن به فایل موقت + rename).
- کش در حافظه + flush در `OnApplicationPause`/`OnApplicationQuit`.

### ۴.۳ `LocalBattleProvider`
- جایگزین `ConnectionManager.LoadBattle` و مچ‌میکینگ.
- انتخاب حریف: سطح آرنا → `BotController.difficulty` + `CalcHeroLevel` + `GetRandomLevel`.
- انتخاب دک حریف از داده `HeroInfos`/`SkinInfo`.
- تولید رویدادهای `MT_OnInitGame`، `MT_OnTurnStart`، `MT_OnSimulateEnemyAction`، `MT_OnBattleResults` به‌صورت محلی (همان کلیدهایی که `RecordedGame` نشان می‌دهد).
- **نوبت‌سازی:** `TurnInfo` موجود + `SyncTurnDuration`؛ مدت ۴۰ ثانیه، حداکثر ۱۵ نوبت (تأییدشده در `loadingScreenHints`).

### ۴.۴ `LocalShopService`
- جایگزین `InAppPurchase` و `Shop.NewShopManager` در سمت پرداخت.
- قیمت‌ها از `ShopInfo` (پکیج جم/طلا) و `ShopItemProfile`.
- «خرید» = کسر ارز درون‌بازی؛ `fakeBuy` موجود در بازی همین رفتار را دارد.
- جایزه ویدیو_ad → «جایزه رایگان» با تأخیر کوتاه (بدون SDK تبلیغات).

### ۴.۵ `LocalEventService`
- رویداد/تورنمنت/لیگ محلی: زمان‌بندی محلی، لیدربورد محلی، جوایز محلی.
- داده از `EventLeagueConfig`، `TournamentList`، `MiniEvents`، `BattlePassConfig`، `TrophyRoadData`.

### ۴.۶ `OfflineGuard` (قطع شبکه)
- حذف/خنثی‌سازی SDKهای شبکه: Socket.IO، Firebase، Unity Services، Ads، AppsFlyer، Metrix، GameAnalytics، Facebook، GPGS، Bazaar/Myket billing.
- **تست:** حالت هواپیما + بررسی ترافیک؛ هیچ درخواستی نباید خارج شود.

---

## ۵. مدل داده

```json
{
  "schemaVersion": 1,
  "player": {
    "name": "بازیکن",
    "arenaIndex": 0,
    "gold": 5000,
    "gem": 100,
    "trophy": 0,
    "maxTrophy": 0,
    "experience": 0,
    "xpLevel": 1,
    "deck": ["Changiz", "Shahin", "Shaboon"],
    "heroes": [{"id":"Changiz","level":1,"ab1":1,"ab2":1,"sp":1,"skins":[]}],
    "unlockedSkins": [],
    "chests": [],
    "boostItems": [],
    "questInfo": {},
    "battlePass": {},
    "trophyRoad": {},
    "settings": {"language":"Fa","music":1.0,"sfx":1.0}
  },
  "stats": {"wins":0,"losses":0,"battles":0},
  "meta": {"createdAt":"...","updatedAt":"...","backupCount":0}
}
```

> نگاشت ۱:۱ با `PlayerProfile` بازی برای اینکه UIهای موجود بدون تغییر کار کنند.

---

## ۶. مدیریت خطا و بازیابی

| خطا | رفتار |
|-----|------|
| خرابی فایل پروفایل | بارگذاری آخرین بکاپ سالم؛ در صورت نبود، پروفایل پیش‌فرض |
| ناسازگاری اسکیما | مهاجرت مرحله‌ای + لاگ |
| کرش در نبرد | بازگشت به منوی اصلی، حفظ پروفایل |
| قطع برنامه ناگهانی | نوشتن atomic + flush در pause |
| کمبود حافظه | پاکسازی کش AssetBundleهای غیرضروری |

---

## ۷. نقشه راه اجرا (مایل‌ستون‌ها)

| # | مایل‌ستون | خروجی | معیار پذیرش |
|---|-----------|-------|-------------|
| **M0** | آزمون بدون پچ روی دستگاه | تشخیص مسیر دیباگ داخلی | آیا با تپ روی `versionText` منوی دیباگ باز می‌شود؟ |
| **M1** | زنجیره ابزار | `tools/il2cpp.py` + `tools/apk.py` | استخراج آدرس متد/فیلد؛ امضای APK معتبر (تأیید با androguard) |
| **M2** | بوت آفلاین | منوی اصلی بدون اینترنت | نصب → منوی اصلی در حالت هواپیما |
| **M3** | نبرد آفلاین | ۳v۳ با AI | یک نبرد کامل، ۱۵ نوبت، پایان و جایزه |
| **M4** | ذخیره محلی | پروفایل + بکاپ | ری‌استارت → پیشرفت حفظ شود |
| **M5** | فروشگاه شبیه‌سازی‌شده | خرید با جم/طلا | کسر/افزایش ارز، بدون پرداخت واقعی |
| **M6** | بسته نهایی | APK arm64 | نصب روی دستگاه، بدون شبکه، پایدار |

**M0 و M1 موازی انجام می‌شوند.** M0 هزینه‌ای ندارد و ممکن است نیاز به پچ را به‌شدت کم کند.

---

## ۸. ریسک‌ها و کاهش آن‌ها

| ریسک | احتمال | اثر | کاهش |
|------|--------|-----|------|
| منوی دیباگ در نسخه منتشرشده غیرفعال باشد | متوسط | بالا | مسیر جایگزین: پچ باینری `offlineMode` |
| پچ باینری بدون decompiler کامل دشوار باشد | بالا | متوسط | ساخت پارسر متادیتا + capstone؛ پچ‌های کوچک و قابل بازگشت |
| ACTk تشخیص تغییر | متوسط | متوسط | غیرفعال‌سازی `ObscuredCheatingDetector` در همان پچ |
| امضای APK نامعتبر | کم | بالا | پیاده‌سازی v1+v2+v3 و اعتبارسنجی با androguard |
| تفاوت رفتار نسخه ۳.۴.۲ با ۳.۳.۷ | - | - | نسخه هدف همان ۳.۴.۲ است |
| عدم امکان تست در سندباکس | قطعی | متوسط | تست روی دستگاه کاربر در هر مایل‌ستون |

---

## ۹. تصمیم‌های ثبت‌شده

| موضوع | تصمیم | تاریخ |
|-------|-------|-------|
| نسخه هدف | 3.4.2 | 2026-11-24 |
| معماری | C — هیبرید (پچ + حفظ باینری) | 2026-11-24 |
| دامنه اولیه | نبرد آفلاین با AI | 2026-11-24 |
| تبلیغات/IAP | فروشگاه شبیه‌سازی‌شده + جایزه رایگان | 2026-11-24 |
| ABI | فقط arm64-v8a | 2026-11-24 |

---

## ۱۰. پرسش‌های باز

1. آیا منوی دیباگ (`versionText` / `ENABLE_DEBUG_MODE`) در نسخه ۳.۴.۲ فعال است؟ → **آزمون M0**
2. آیا `offlineMode` به‌تنهایی کل جریان (منو + نبرد + ذخیره) را پوشش می‌دهد یا فقط ورود را؟ → آزمون M0/M2
3. آیا `TestersCustomProfileManager` پروفایل را از فایل محلی می‌خواند؟ → تحلیل کد در M1
4. رفتار دقیق `BotController.difficulty` نسبت به آرنا → آزمون M3

---

> **قدم بعدی:** اجرای M0 (تست روی دستگاه کاربر) و شروع M1 (زنجیره ابزار) پس از تأیید این سند.
