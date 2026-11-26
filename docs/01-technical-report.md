# گزارش فنی جامع — مرحله ۱
## تحلیل بازی اندرویدی «پسرخوانده / Mafioso: Godfather of Mafia City»

> **تاریخ:** 2026-11-24
> **نسخه هدف:** 3.4.2 (Cafe Bazaar) — جدیدتر از 3.3.7
> **وضعیت:** تحلیل اولیه کامل شد. **هیچ تغییری در بازی، منابع یا کد اعمال نشده است.**
> **هدف:** تعیین معماری، وابستگی‌ها، قابلیت‌های قابل بازسازی، محدودیت‌ها و نقشه راه پیش از هرگونه پیاده‌سازی.

---

## ۰. خلاصه مدیریتی

| موضوع | یافته |
|-------|-------|
| موتور بازی | **Unity 6 — 6000.0.58f2** با بک‌اند **IL2CPP** (ARM64) |
| نوع بازی | استراتژی نوبتی (Turn-based Strategy) با المان‌های نقش‌آفرینی و کارت |
| معماری | کلاینت-سرور: **Socket.IO** + REST + Firebase + Unity Services |
| سرور اصلی | `android.pesarkhandeh.ir:443` (پینگ‌تست: `/ping-test`) |
| حجم منابع | ۲۶۱ مگابایت داده Unity + ۲۸ مگابایت بسته صوتی فارسی |
| منابع گرافیکی/صوتی | ۷۰۴ Texture2D، ۴٬۴۵۷ Sprite، ۱٬۲۲۵ AudioClip، ۲٬۰۱۷ AnimationClip، ۵۴۳ AnimatorController |
| داده بازی | ۴۰ قهرمان، ۷۷ اسکین، ۱۸ صندوق، ۱۳ آرنا، ۳۶ جایزه Battle Pass، ۷۱ جایزه Trophy Road |
| ذخیره‌سازی | `PlayerProfile` / `SaveSystem` + `ObscuredPrefs` (Anti-Cheat Toolkit) + همگام‌سازی سرور |
| وابستگی بحرانی | Socket.IO برای ورود، مچ‌میکینگ، درفت، نبرد، چت کلن، فروشگاه و جوایز |
| قابلیت بازسازی | UI/صدا/انیمیشن/داده: **بالا** — منطق نبرد: **متوسط** — سرور اصلی: **بازسازی تقریبی** |
| توصیه | نسخه آفلاین با **موتور نبرد محلی + هوش مصنوعی** و استفاده از منابع استخراج‌شده؛ پچ کامل APK به‌عنوان گزینه دوم |

> **نکته مهم:** نسخه‌ای که از Cafe Bazaar دریافت شد **3.4.2** است (جدیدتر از 3.3.7 درخواستی). APKPure برای این پکیج فقط نسخه **2.8.0** را به‌صورت APK یکپارچه (Universal) ارائه می‌دهد. هر دو در `original/` نگهداری می‌شوند.

---

## ۱. فایل‌های ورودی و هش‌ها

| فایل | حجم (بایت) | SHA-256 |
|------|-----------:|---------|
| `original/pesarkhande-3.4.2-base.apk` | 129,977,246 | `94a9beca7ae0025062bb1f5ed76541e8a7d1df41054cc491b1b9f5325d67643b` |
| `original/pesarkhande-3.4.2-split_config.arm64_v8a.apk` | 27,993,663 | `e47f734399c489d92b65270a141603e80eb956fac1a086d6ec1efb2ee4b29370` |
| `original/pesarkhande-2.8.0-apkpure.apk` | 146,449,030 | `4c8c511b652ea640ef6e915a14c04c46b39b0309f9a2a4a23b6204542c985f14` |
| `original/bazaar_reply.json` | 7,901 | متادیتای پاسخ Cafe Bazaar (نسخه، splits، CDN) |

**امضای دیجیتال (هر سه APK):**
- Subject/Issuer: `Organization: Paeezan Studio`
- Serial: `1688900120`
- اثر انگشت SHA-256 گواهی: `96:F7:3E:0A:73:F6:7E:CE:A3:70:6E:DC:D9:C0:63:3D:3D:11:D7:AE:A5:34:C2:93:44:D6:27:6B:8D:73:A0:A2`

**نصب نسخه 3.4.2:**
```bash
adb install-multiple original/pesarkhande-3.4.2-base.apk \
  original/pesarkhande-3.4.2-split_config.arm64_v8a.apk
```

> نسخه 2.8.0 یک APK کامل و مستقل (شامل کتابخانه‌های بومی) است و به‌عنوان fallback برای مقایسه/تحلیل نگه داشته شده است.

---

## ۲. مشخصات APK (نسخه 3.4.2)

| مشخصه | مقدار |
|-------|-------|
| Package | `com.paeezanstudio.pesarkhande` |
| نام برنامه | پسرخوانده (Bazaar) / Mafioso (APKPure 2.8.0) |
| versionName | `3.4.2` |
| versionCode | `3420004` |
| minSdk / targetSdk | 23 / 36 |
| Activity اصلی | `com.trophit.MyUnityPlayerActivity` |
| Activities / Services / Receivers / Providers | 69 / 25 / 29 / 12 |
| Permissions | 39 |
| Split | `config.arm64_v8a` — `hasCode=false`، `extractNativeLibs=true` |
| ABI | arm64-v8a (split) |
| تعداد فایل‌های base | 8,117 |
| تعداد فایل‌های split | 20 |
| حجم نصب | ~158 مگابایت (156,283,389 بایت طبق Bazaar) |

**دسترسی‌های مهم:** `INTERNET`، `ACCESS_NETWORK_STATE`، `ACCESS_WIFI_STATE`، `com.android.vending.BILLING`، `com.farsitel.bazaar.permission.PAY_THROUGH_BAZAAR`، `POST_NOTIFICATIONS`، `AD_ID`، `WAKE_LOCK`، `VIBRATE`.

---

## ۳. موتور بازی و معماری باینری

### ۳.۱ موتور
- **Unity 6 (6000.0.58f2)**
- **IL2CPP** (بدون Mono)
- `libil2cpp.so`: 49,008,720 بایت
- `libunity.so`: 22,035,680 بایت
- `global-metadata.dat`: 14,003,588 بایت — **نسخه ۳۱**
- سایر کتابخانه‌های بومی: Firebase C++ (Analytics/App/Crashlytics/Messaging)، `lib_burst_generated.so`، `libmain.so`، `libnative-lib.so`، `libpl_droidsonroids_gif.so`

### ۳.۲ صحنه‌ها (Scenes)
```
Assets/_Scene/Paeezan_MotionLogo.unity
Assets/_Scene/LoadingScreen.unity
Assets/_Scene/ConnectionScreen.unity
Assets/_Scene/MainMenu.unity
Assets/_Scene/Arena_1.unity ... Arena_13.unity
Assets/_Scene/Arena_1_TutIntro.unity
Assets/_Scene/CustomArena.unity
```
۱۹ صحنه: لوگو، لودینگ، اتصال، منوی اصلی، ۱۳ آرنا، آموزش آرنا ۱، آرنا سفارشی.

### ۳.۳ ساختار کد (MonoScript)
- **۳٬۷۸۴** MonoScript در کل
- **۱٬۵۷۰** کلاس در `Assembly-CSharp` (کد اصلی بازی)
- **۵۰** کلاس در `SocketIOUnityAssembly`
- ۴۷ کلاس در `ACTk.Runtime` (Anti-Cheat Toolkit)
- ۴۶ کلاس در `Google.Play.Games`
- ۲۴ کلاس در `Facebook.Unity.dll`
- ۲۴ کلاس در `TapsellMediation`
- ۱۸ کلاس در `AppsFlyer`
- ۲۱ کلاس در `Unity.Purchasing.PaymentProviderService` + ۴۳ در `WebshopService`

**کلاس‌های کلیدی بازی:**
```
SaveSystem, PlayerProfile, PlayerData, CustomProfileData, ProfileStats
ConnectionManager, ConnectionAddressProvider, SocketIOComponent, SocketIOPersistentEvent
Card, Hero, DeckHero, DeckManager, CardsCollectManager
BattleKeywordHandler, BattleLogMenu, BattleReward, BattleResourceProvider
ChestScript, ChestCardsScript, ChestPopupManager
QuestManager, QuestInfo, FreeQuest, QuestSlot, QuestPrize
ClanManager, ClanInfo, ClanMessage, ClanWarMenuScript, ClanWarInfoPopUp
Shop.NewShopManager, Shop.ShopSettings, ShopItemProfile
TournamentMenuManager, EventLeagueManager, EventLeagueLeaderboardItem
TrophyRoadUI, BattlePassPanel, PiggyBankRewardMenu
ReplayEventsProxy, VideoAdManager, InAppPurchaseManager
```

### ۳.۴ IL2CPP
- متادیتا نسخه ۳۱ (سازگار با Unity 6).
- نام کلاس‌ها/متدها/فیلدها در `global-metadata.dat` موجود است.
- استخراج نام‌ها انجام شد: **۱۱۴٬۱۴۱** رشته در جدول نام‌ها و **۲۳٬۲۷۰** String Literal.
- **ابزار decompile کامل (Il2CppDumper/Cpp2IL) در سندباکس موجود نیست** (نیازمند .NET). تحلیل فعلی بر اساس متادیتا، رشته‌ها، Assetها و Configها است.

---

## ۴. ساختار منابع (Unity Assets)

### ۴.۱ آمار کلی
| نوع | تعداد |
|-----|------:|
| Texture2D | 704 |
| Sprite | 4,457 |
| AudioClip | 1,225 |
| AnimationClip | 2,017 |
| AnimatorController | 543 |
| TextAsset | 78 |
| MonoScript | 3,859 |
| MonoBehaviour | 132,906 |
| GameObject | 112,539 |
| Font | 5 |
| Mesh | 152 |
| Shader | 272 |
| Material | 505 |
| SpriteAtlas | 28 |
| ParticleSystem | 6,596 |

### ۴.۲ حجم‌ها
| مسیر | حجم |
|------|-----:|
| `assets/bin/Data` | ۲۶۱ مگابایت (۶٬۰۸۹ فایل) |
| `assets/voices_bundle_fa` | ۲۸ مگابایت (بسته صدای فارسی) |
| `lib/arm64-v8a` | ۷۷ مگابایت (split) |
| `assets/ad-viewer` | وب‌ویو تبلیغات |
| `assets/audience_network.dex` | ۳.۳ مگابایت (Facebook Audience Network) |

### ۴.۳ فونت‌ها
- Vazir (Regular/Bold)
- B Koodak (`bkoodb.ttf`)
- Adivery Dana (`adivery_dana_normal.ttf`)
- فونت‌های سیستمی Unity/TMP

### ۴.۴ زبان‌ها
- **۱۳ زبان:** فارسی (Fa)، انگلیسی (En)، روسی (Ru)، آلمانی (De)، اسپانیایی (Es)، فرانسوی (Fr)، عربی (Ar)، ایتالیایی (It)، لهستانی (PL)، ترکی (Tr)، چینی ساده (Cns)، چینی سنتی (Cnt)، پرتغالی (PT)
- `Localization`: **۶٬۴۳۳ ردیف** × ۱۳ زبان (۱.۸۹ مگابایت)
- `SmartHintsTranslations`: ۱۶۷ کیلوبایت
- `loadingScreenHints`: ۴۳ کیلوبایت

---

## ۵. داده‌های بازی (TextAssets / Configs)

| فایل | حجم | توضیح |
|------|-----:|-------|
| `HeroInfos` | 301 KB | جدول CSV قهرمانان: نام، توضیح، ۲ توانایی + ۱ ویژه (SP) در ۱۳ زبان — ۴۱۹ ردیف داده، ۴۰ قهرمان |
| `HeroInfos_OLD` | 36 KB | نسخه JSON قدیمی اطلاعات قهرمانان |
| `HeroAbilityInfos` | 6.3 KB | نگاشت هر قهرمان به کلیدواژه‌های توانایی (keyword IDs) |
| `SkinInfo` | 216 KB | ۷۷ اسکین، نوع A/B/C/X، تعداد fragment، لینک CDN |
| `ShopInfo` | 18 KB | هزینه کارت، هزینه صندوق، پکیج جم/طلا، ۹ بنل آرنا |
| `ShopItemProfile` | 22 KB | پیشنهادهای روزانه، ویژه، استارترپک، اشتراک |
| `ChestInfo` | 31 KB | ۱۷ نوع صندوق و پارامترهای آن‌ها |
| `ChestCards` | 1 KB | نمونه کارت‌های صندوق |
| `ArenaInfo` | 1.3 KB | ۱۳ آرنا + ۵ آرنای آموزشی + `BotMaxTrophy=2900` |
| `BattlePassConfig` | 40 KB | BP_001، قیمت ۱۲٬۴۰۰، ۳۶ جایزه، Gold Bank |
| `TrophyRoadData` | 12 KB | ۷۱ جایزه + ۲۹ VIP + ۴ Announcer |
| `EventLeagueConfig` | 19 KB | تنظیمات مسابقه، تبادل، داستان، سفارشی‌سازی |
| `TournamentList` | 2.1 KB | ۲ تورنمنت فعال |
| `MiniEvents` | 10 KB | ۱ Chain Offer + Joker Offer با ۱۵ کلید |
| `ClanConfig` | 12 KB | هزینه ساخت کلن، ظرفیت، اجاره، دونیشن، جنگ کلن (۲۳ کلید) |
| `ClanInfo` | 76 KB | نمونه اطلاعات کلن و پیام‌ها |
| `PlayerProfile` | 50 KB | پروفایل نمونه/پیش‌فرض (طلا، جم، جام، دسته، قهرمانان، صندوق‌ها) |
| `LeaderBoard` | 14 KB | نمونه لیدربورد |
| `BattleLogResponse` | 10 KB | ساختار تاریخچه نبرد |
| `RecordedGame` | 17 KB | نمونه ری‌پلی کامل یک نبرد (۶۶ رویداد) |
| `SyncPacket` | 298 B | بسته همگام‌سازی نبرد |
| `GameData` | 687 B | تنظیمات ویدیو اد و ارجاع (Referral) |
| `GameVersion` | 71 B | `3420004` |
| `Localization` | 1.9 MB | تمام رشته‌های UI در ۱۳ زبان |
| `SmartHintsTranslations` | 167 KB | راهنمای هوشمند |
| `loadingScreenHints` | 44 KB | نکات صفحه لودینگ |

---

## ۶. سیستم‌های بازی

### ۶.۱ قهرمانان، کارت‌ها و دسته
- **۴۰ قهرمان** با نام فارسی/انگلیسی (مثلاً چنگیز انفرادی = Stefano Solo، شهین تکتیر = Deb Deathshot، ننجون = Granny).
- هر قهرمان: **۲ توانایی معمولی (Ab1/Ab2) + ۱ توانایی ویژه (SP)**، سطح قهرمان، سطح توانایی‌ها، اسکین، اجاره/قرض.
- **کارت‌ها:** ۴ سطح کمیابی؛ `CARDBUYLIMITS=[100,100,15,3]` و `CARDCOSTMULTIPLIER=[5,5,250,12000]`.
- **اسکین‌ها:** ۷۷ اسکین؛ fragment تکراری: A=5، B=10، C=16، X=16.
- **Deck:** ۳ اسلات قهرمان در هر نبرد (نمونه `EndDraft` و `RecordedGame`).
- **اجاره قهرمان:** `borrowUsageTime=86400000` (۲۴ ساعت)، `rentRefreshTime=108000000` (۳۰ ساعت)، `borrowRefreshTime=172800000` (۴۸ ساعت)، ضریب هزینه قهرمان جدید = ۴.

### ۶.۲ نبرد (Battle)
- **نوبتی (Turn-based)**، ۳ قهرمان در هر طرف، حداکثر **۱۵ نوبت** (طبق loading hints).
- ساختار `SyncPacket`:
```json
{
  "healths": [240,240,0,168,0,186],
  "abilitieEffects": [null,...],
  "ACArgs": [null,...],
  "LCArgs": {
    "pLastPlay": 1, "eLastDead": 4, "pLastDead": 2,
    "TD": 30, "TR": 27.61752, "TN": 5,
    "PS": 1, "ES": 1, "syncIndex": 0
  },
  "pManaRage": [3,8.9775],
  "eManaRage": [0,5.985],
  "Projectiles": null
}
```
- رویدادهای ری‌پلی (`RecordedGame`):
  - `initgame` — شروع نبرد (roomID، جام حریف، isMaster، اجازه تسلیم)
  - `spawnUnits` — کارت‌های من و حریف (heroId، heroLvl، ab1Lvl، ab2Lvl، spLvl، isRented، skin)
  - `turnstart` — شماره نوبت (TN) و مدت (TD=40)
  - `simulateenemyaction` — FP, SP, IE, AT, RND, TN, AI
  - `turnend`
  - `battleresult`
- **درفت (Draft):** `MT_StartDraft`، `MT_StartDraftTurn`، `MT_RivalPick`، `MT_RivalBan`.
- **تسلیم:** حداکثر ۵ بار در روز.
- **Battle Log:** roomID، نام/کلن/جام بازیکنان، قهرمانان، کشته‌شده‌ها، جام کسب‌شده.

### ۶.۳ آرنا، جام و پیشرفت
- **۱۳ آرنا** بر اساس بازه جام (۰–۴۰۰، ۴۰۰–۸۰۰، ... تا ۲٬۹۰۰ برای Bot).
- پاداش طلای هر آرنا: ۵، ۷، ۹، ۱۱، ۱۲، ۱۴، ...
- **Trophy Road:** ۷۱ جایزه معمولی + ۲۹ VIP + ۴ Announcer.
- **Arena Upgrade / Arena Bundle:** ۹ بنل با قیمت ۷٬۴۰۰ تا ۹۹٬۹۰۰ تومان.
- **XP و Level:** `experience`, `xpLevel`, `minRequiredXp=70` برای کلن.

### ۶.۴ صندوق‌ها
- **۱۷ نوع:** Tutorial1/2، Shop1/2، Free، Wooden، Silver، Crown، Giant، Magical، SuperMagical، Rent، LeaderBoard، Tournament، Tournament2، Fortune، PiggyBankV2.
- پارامترها: `pickCardCount`، `cardTypeCount`، `time`، `videoReward`، تعداد کارت هر آرنا.
- صندوق‌های رایگان روزانه، Crown Chest، Fortune Chest، Piggy Bank.

### ۶.۵ فروشگاه و اقتصاد
- **ارزها:** Gold، Gem، Trophy، XP، ارز Event League.
- **پکیج جم (تومان):** ۲٬۴۰۰→۸۰، ۱۲٬۴۰۰→۵۰۰، ۲۹٬۹۰۰→۱٬۲۰۰، ۴۹٬۹۰۰→۲٬۵۰۰، ۱۲۴٬۹۰۰→۶٬۵۰۰، ۲۴۹٬۹۰۰→۱۴٬۰۰۰.
- **پکیج طلا:** ۶۰→۱٬۰۰۰، ۵۰۰→۱۰٬۰۰۰، ۲٬۴۰۰→۵۰٬۰۰۰.
- پیشنهادهای روزانه/ویژه، استارترپک، اشتراک، Battle Pass، Skin Offer، Multi-Skin Offer، Hero Upgrade Offer، Fortune Chest، Piggy Bank.
- **IAP:** Bazaar Billing، Myket، Google Play Billing، Unity IAP، Webshop.

### ۶.۶ مأموریت‌ها و دستاوردها
- `QuestManager`، `QuestInfo`، `FreeQuest`، `QuestSlot`، `QuestPrize`، `QuestProgressHandler`.
- Quest Point Boost، ریست روزانه (`DailyResetSaveKey`)، اعلان مأموریت.
- لیدربورد فصلی، Event League، Battle Pass.

### ۶.۷ کلن و جنگ کلن
- ساخت کلن: ۱٬۰۰۰ جم؛ حداکثر ۵۰ عضو؛ حداقل گام جام ۵۰۰؛ حداقل XP ۷۰.
- سیستم اجاره/قرض قهرمان، دونیشن، چت کلن، پیام‌های کلن.
- **Clan War:** روز نبرد/روز جمع‌آوری، نقشه، لیگ، لیدربورد، جوایز لیگ.
- کلاس‌ها: `ClanWarMenuScript`، `ClanWarInfoPopUp`، `ClanWarMapButton`، `ClanWarLeaderBoard*`، `ClanWarPastWar*`.

### ۶.۸ رویدادها و تورنمنت‌ها
- **Event League:** تنظیمات اصلی، مسابقه، تبادل (Exchange)، داستان، سفارشی‌سازی؛ لیدربورد و تیترها.
- **Tournament:** ۲ تورنمنت (از جمله Death Mode و تورنمنت‌های فصلی) با winCount، savedWinCount، saveProgress.
- **Mini Events:** Chain Offer، Joker Offer (۱۵ کلید)، Daily Gem، Free Chest، Hero Boost.

### ۶.۹ اسکین‌ها
- ۷۷ اسکین، ۴ نوع (A/B/C/X)، fragment، لینک CDN، نسخه AssetBundle.
- Skin Offer، Multi-Skin Offer، Skin Announcement، Skin Voice Asset.
- رندر اسکین با RenderTexture (`PrivateSkinRenderToTextureHelper`).

---

## ۷. وابستگی‌های آنلاین

### ۷.۱ Socket.IO — وابستگی بحرانی
- **آدرس:** `android.pesarkhandeh.ir:443`
- **مسیر:** `/socket.io` (پیش‌فرض Socket.IO)
- **پینگ‌تست:** `https://android.pesarkhandeh.ir/ping-test`
- **تنظیمات Pool:**
```json
{
  "urls": [{"url": "android.pesarkhandeh.ir:443", "testUrl": "https://android.pesarkhandeh.ir/ping-test"}],
  "pingCount": 3, "pingTimeout": 1500, "connectToBest": true, "goodPingThreshold": 200
}
```
- **رویدادهای Socket.IO (`MT_*`):**
  - اتصال/ورود: `MT_OnConnected`, `MT_OnLoggedIn`, `MT_OnJoinroom`, `MT_OnConnectionProblem`, `MT_OnDesynced`, `MT_OnDoSync`, `MT_OnRequestSyncPacket`, `MT_OnMafiosoPing`, `MT_OnLinkAcc`, `MT_OnNews`
  - نبرد: `MT_OnInitGame`, `MT_StartDraft`, `MT_StartDraftTurn`, `MT_RivalPick`, `MT_RivalBan`, `MT_OnTurnStart`, `MT_OnTurnEnd`, `MT_OnSimulateEnemyAction`, `MT_OnSimulateMyPlayerAction`, `MT_SyncTurnDuration`, `MT_OnBattleResults`, `MT_OnEnemyConnected`, `MT_OnEnemyDisconnected`
  - متا: `MT_OnTrophyChanged`, `MT_OnStat`, `MT_OnLeaderBoard`, `MT_OnShopItems`, `MT_OnSetRewards`, `MT_OnChestCards`, `MT_OnBoostAdded`, `MT_OnActivateBattlePassResponse`, `MT_OnActivateEventLeagueResponse`
  - کلن: `MT_OnClanInfo`, `MT_OnClanMessage`, `MT_OnClanSearchResult`, `MT_ClanMembersOnlineStatusUpdate`, `MT_ClanTrophyUpdate`, `MT_ClanWarTrophyUpdate`, `MT_ClanWarnMsg`
  - خرید/اجاره: `MT_BuyConfirm`, `MT_BuySpecialOfferResponse`, `MT_AddToHeroRentList`, `MT_RemoveFromHeroRentList`, `MT_OnRentedHeroUpdated`
  - صدا: `MT_SimulateEnemyVCMessage`, `MT_SimulateMyPlayerVCMessage`
  - بستن: `MT_Close`

### ۷.۲ REST API و پیکربندی سرور
- `ConnectionAddressProvider`: دانلود پیکربندی آدرس سرور، پینگ چند سرور، انتخاب بهترین (بر اساس کشور).
- `ConnectionManager`: ورود/ثبت‌نام (`signin`, `signup`)، اتصال مجدد، `softUpdate`، `LoadBattle roomID`.
- API Clientها: `ClientApiClient`، `PaymentProviderApiClient`، `WebshopLinkApiClient`، `BaseApiClient`، `DefaultHttpClient`.
- آدرس‌های مشاهده‌شده:
  - `https://pesarkhandeh.com/v3-update-panel`
  - `https://support-mafioso.pesarkhandeh.com/`
  - `http://log.pesarkhandeh.com:8080/upload`
  - `https://pesarkhande.com/clan/?id={0}&market={1}`
  - `https://pesarkhande.com/replay/?id={0}&market={1}`
  - `https://pesarkhande.com/DL/mafioso.html`
- تشخیص IP/کشور: `api.country.is`، `api.findip.net`، `api.ipify.org`، `ipapi.co`.

### ۷.۳ Firebase
- **Project:** `pesarkhande-c6a7b` (شماره ۷۴۸۱۸۵۶۰۴۰۲۲)
- **Realtime Database:** `https://pesarkhande-c6a7b.firebaseio.com`
- **Storage:** `pesarkhande-c6a7b.appspot.com`
- **سرویس‌ها (در کد/manifest):** Auth، Database/Firestore، Functions، Messaging، Analytics، Crashlytics، Installations، Sessions، Dynamic Links، Remote Config، Storage، VertexAI (احتمالاً استفاده‌نشده).
- **کلید API کلاینت:** در `assets/google-services-desktop.json` — کلید عمومی است اما در مستندات باید حذف/ماسک شود.

### ۷.۴ Unity Services
- Analytics (`collect.analytics.unity3d.com`)
- IAP (`iap.services.api.unity.com`, `iap-stg.services.api.unity.com`)
- Live Content / Remote Catalog (`services.api.unity.com/live-content/client/v1`)
- Webshop (`webshop.services.api.unity.com`, `webshop-stg.services.api.unity.com`)
- Unity Cloud Project: `production` environment

### ۷.۵ تبلیغات (Ads)
| شبکه | وضعیت در 3.4.2 |
|-------|-----------------|
| Google AdMob | ✅ |
| AppLovin MAX | ✅ |
| IronSource / LevelPlay | ✅ |
| MintBridge (MBridge) | ✅ |
| Facebook Audience Network | ✅ |
| Unity Ads | ✅ |
| Tapsell | ✅ |
| Adivery | ✅ |
| Chartboost | در 2.8.0 |
| Vungle / AdColony | در 2.8.0 |
| Hyperbid / TopOn / TradPlus | رشته‌های مدیریتی |

### ۷.۶ پرداخت درون‌برنامه‌ای (IAP)
- Bazaar Billing (`com.farsitel.bazaar`)، Myket، Google Play Billing (`com.android.vending.BILLING`)
- Unity IAP / Purchasing
- Webshop
- کلاس‌ها: `purchesFlow.PSK_Purchase`، `BazaarPlugin`، `MyketPlugin`، `InAppPurchaseManager`

### ۷.۷ تحلیل و اتتریبیوشن
- AppsFlyer، Yandex AppMetrica، Metrix (`ir.metrix`)، GameAnalytics، myTracker، Unity Analytics، Firebase Analytics.
- Facebook SDK (ورود، اشتراک‌گذاری، تبلیغات).
- Google Play Games و Google Sign-In.

### ۷.۸ CDN و منابع راه‌دور
- `https://cdn.mafioso-game.com` — AssetBundleها، تصاویر پاپ‌آپ، Pool Config.
- `https://cdn.mafioso-game.com/Pools/V2/android-ir-pool.json` — پیکربندی سرور.
- لینک‌های Discord برای برخی بنرها/AssetBundleها (در Configها).
- برخی AssetBundleها در APK نیستند و باید در زمان اجرا دانلود شوند.

---

## ۸. سیستم ذخیره‌سازی

### ۸.۱ اجزا
- `SaveSystem` — مدیریت ذخیره/بارگذاری
- `PlayerData` / `IPlayerData` — داده بازیکن
- `PlayerProfile` — مدل کامل پروفایل
- `CustomProfileData` — پروفایل سفارشی
- `ProfileStats` — آمار
- `ObscuredPrefs` (ACTk) — لایه امن PlayerPrefs
- `PlayerPrefs` — ذخیره‌سازی ساده
- `SaveData`، `LoadProfile`، `OnSaveDataSucceed`، `OnSaveDataFailed`، `UploadData`

### ۸.۲ ساختار `PlayerProfile` (نمونه)
```json
{
  "eventLeague": {...23 کلید...},
  "inventory": {...},
  "BattlePass": {...9 کلید...},
  "BattlePassClaimableBanks": [...],
  "piggyBank": {...5 کلید...},
  "boostedHero": {...3 کلید...},
  "arenaIndex": 5,
  "gold": 5000,
  "experience": 3710,
  "gem": 100000,
  "trophy": 450,
  "maxTrophy": 810,
  "isBattlePassFeatureAvailable": true,
  "deck": [3 قهرمان],
  "heroes": [39 قهرمان],
  "unlockedSkins": [],
  "chests": [4 صندوق],
  "freeChests": {...},
  "crownChest": {...},
  "boostItems": [...6...],
  "trophyRoad": {...},
  "questInfo": {...21 کلید...},
  "donationInfo": {...},
  "hasAvailableTournament": true,
  "subscriptionState": {...},
  "borrowedHero": {...},
  "shopPreferences": {...},
  "dailyGem": {...},
  "reservedDailyGem": [...],
  "nativeAd": {...}
}
```
> این پروفایل **نمونه/تستی** است و لزوماً مقدار پیش‌فرض بازی نیست.

### ۸.۳ همگام‌سازی
- ورود: `MT_OnLoggedIn`
- همگام‌سازی: `MT_OnDoSync`، `MT_OnRequestSyncPacket`، `MT_OnDesynced`
- ذخیره در Firebase/سرور و کش محلی.
- کلیدهای ObscuredPrefs مشاهده‌شده: `language_save`، `logs.save`، `earlyGamePopupSave`، `EarlyGamePopupConfigSaveKey`، `DailyResetSaveKey`، `AppleLinkStatusSaveKey`، `BazaarLinkStatusSaveKey`، `GoogleLinkStatusSaveKey`، `GameUpLinkStatusSaveKey`، `GameUpTokenSaveKey`.

### ۸.۴ نتیجه برای نسخه آفلاین
- باید **SaveSystem محلی** با همان مدل `PlayerProfile` ساخته شود (SQLite یا JSON + بکاپ).
- کلیدهای ObscuredPrefs باید با ذخیره‌سازی امن محلی جایگزین شوند.
- همگام‌سازی سرور حذف و با نسخه محلی جایگزین شود.

---

## ۹. پروتکل نبرد (جزئیات فنی)

### ۹.۱ رویدادهای ری‌پلی
```
initgame:
  EN, enemyTrophy, isMaster, roomID, isSurrenderAvailable,
  noSurrenderReason[], myDeck[], rivalDeck[], arenaIndex, ...

spawnUnits:
  myDeck[{heroId, heroLvl, ab1Lvl, ab2Lvl, spLvl, isRented, skin}],
  rivalDeck[...]

turnstart: {TN, TD}
simulateenemyaction: {FP, SP, IE, AT, RND, TN, AI}
turnend: {TN}
battleresult: {winner, trophies, rewards, ...}
```

### ۹.۲ `SyncPacket`
- `healths[6]` — جان ۳ قهرمان من + ۳ قهرمان حریف
- `abilitieEffects[6]` — افکت‌های فعال
- `ACArgs[6]` — آرگومان‌های Ability Command
- `LCArgs` — وضعیت نوبت: آخرین بازی/مرگ، شماره نوبت، مدت، شاخص همگام‌سازی
- `pManaRage[2]` / `eManaRage[2]` — مانا/خشم من و حریف
- `Projectiles` — پرتابه‌ها

### ۹.۳ نکات ناشناخته (نیازمند تحلیل بیشتر)
- فرمول دقیق آسیب، درمان، مانا/خشم، افکت‌های توانایی‌ها.
- ترتیب و اولویت کارت‌ها در درفت.
- منطق هوش مصنوعی حریف (`AI` در `simulateenemyaction`).
- محاسبه جام/جوایز پایان نبرد.
- رفتار سرور در تسلیم، قطع اتصال، Desync.

---

## ۱۰. ماتریس قابلیت‌های قابل بازسازی

| قابلیت | منبع داده | امکان‌سنجی | توضیح |
|--------|-----------|-----------:|-------|
| منوی اصلی و UI | Prefab/Texture/Animation | **بالا** | Assetهای کامل در APK |
| قهرمانان و کارت‌ها | HeroInfos + Asset | **بالا** | ۴۰ قهرمان، ۷۷ اسکین |
| نبرد | Config + Replay + UI | **متوسط-بالا** | منطق دقیق نیاز به تحلیل/decompile |
| آرنا و جام | ArenaInfo + TrophyRoad | **بالا** | داده کامل |
| صندوق‌ها | ChestInfo | **بالا** | ۱۷ نوع |
| فروشگاه و اقتصاد | ShopInfo/ShopItemProfile | **بالا** | قیمت‌ها و پکیج‌ها موجود |
| مأموریت‌ها | Quest* classes + Config | **متوسط** | نیاز به تحلیل منطق |
| Battle Pass | BattlePassConfig | **بالا** | ۳۶ جایزه |
| Event League | EventLeagueConfig | **متوسط** | نیاز به شبیه‌سازی رویداد |
| تورنمنت | TournamentList | **متوسط** | ۲ تورنمنت |
| کلن / جنگ کلن | ClanConfig + کلاس‌ها | **متوسط** | نیاز به کلن محلی/شبیه‌سازی |
| اسکین‌ها | SkinInfo + CDN | **بالا** | برخی AssetBundleها راه‌دور |
| صدا و انیمیشن | AudioClip/AnimationClip | **بالا** | ۱٬۲۲۵ صدا، ۲٬۰۱۷ انیمیشن |
| ذخیره‌سازی | PlayerProfile | **بالا** | بازنویسی محلی |
| ورود/پروفایل | ConnectionManager | **بالا** | پروفایل محلی |
| مچ‌میکینگ/نبرد آنلاین | Socket.IO | **متوسط** | جایگزینی با AI |
| لیدربورد آنلاین | LeaderBoard | **بالا** | لیدربورد محلی |
| IAP | Unity IAP/Bazaar | **بالا** | فروشگاه شبیه‌سازی‌شده |
| تبلیغات | Ad SDKs | **بالا** | حذف/جایگزینی |
| Firebase | Firebase SDK | **بالا** | حذف/جایگزینی محلی |

---

## ۱۱. محدودیت‌ها و ریسک‌ها

1. **عدم دسترسی به decompiler کامل IL2CPP** در سندباکس (نیازمند .NET). تحلیل فعلی بر اساس متادیتا/رشته/Config/Asset است.
2. **منطق سمت سرور** (مچ‌میکینگ، اعتبارسنجی اقتصاد، ضد تقلب، جوایز) در دسترس نیست؛ باید بازسازی شود.
3. **برخی AssetBundleها راه‌دور هستند** (CDN/Discord) و در APK نیستند؛ باید دانلود شوند.
4. **امضای APK** با تغییر شکسته می‌شود؛ نیاز به امضای مجدد (debug/کلید شخصی) و احتمال شکست SDKها.
5. **Anti-Cheat Toolkit (ACTk)** ممکن است تغییرات را تشخیص دهد؛ باید حذف/غیرفعال شود.
6. **Split APK** نیاز به نصب چندتایی دارد (`adb install-multiple` یا SAI).
7. **Firebase Rules/REST API** ناشناخته است؛ بازتولید دقیق سرور ممکن نیست.
8. **حقوقی:** Assetها متعلق به Paeezan Studio/Herocraft هستند؛ استفاده فقط برای نسخه شخصی و آفلاین، بدون بازنشر عمومی.
9. **Unity 6 / Metadata v31:** ابزارهای قدیمی Il2CppDumper ممکن است سازگار نباشند.
10. **پایداری:** تغییر APK ممکن است باعث کرش/رفتار غیرمنتظره شود؛ باید مرحله‌به‌مرحله تست شود.

---

## ۱۲. گزینه‌های معماری نسخه آفلاین

### گزینه A — پچ APK + سرور محلی (بالاترین وفاداری، سخت‌ترین)
- پچ `ConnectionAddressProvider` به `127.0.0.1`، اجرای سرور Socket.IO/REST/Firebase Emulator محلی.
- **مزیت:** UI و منطق اصلی دست‌نخورده.
- **عیب:** باید پروتکل سرور دقیق بازسازی شود؛ ضد تقلب/امضا؛ Split APK.

### گزینه B — بازسازی کلاینت با منابع استخراج‌شده
- ساخت کلاینت جدید (Unity/Godot) با Texture/Audio/Animation/Configهای استخراج‌شده.
- **مزیت:** کنترل کامل، آفلاین واقعی، بدون سرور.
- **عیب:** بازنویسی UI/منطق؛ احتمال عدم تطابق دقیق.

### گزینه C — هیبرید (توصیه‌شده برای شروع)
- پچ APK برای رد کردن ورود و اجرای نبرد محلی در برابر AI، حفظ UI/Assetها.
- **مزیت:** تلاش متوسط، وفاداری بالا.
- **عیب:** نیاز به هوک/جایگزینی لایه شبکه.

**توصیه:** شروع با **گزینه C** برای پروتایپ نبرد آفلاین، سپس در صورت نیاز مهاجرت به **گزینه B** برای سیستم‌های متا. گزینه A فقط در صورت امکان بازسازی کامل پروتکل.

---

## ۱۳. نقشه راه پروژه

| فاز | عنوان | خروجی | وضعیت |
|-----|-------|-------|--------|
| ۰ | آماده‌سازی و دریافت APK | APK + هش + ابزار | ✅ |
| ۱ | تحلیل و مستندسازی | این گزارش | ✅ |
| ۲ | طراحی معماری و استخراج منابع | Data Model + Asset Pipeline + Save محلی | ⏳ |
| ۳ | بوت آفلاین (رد کردن ورود) | منوی اصلی بدون اینترنت | ⏳ |
| ۴ | پروتایپ نبرد | ۳v۳ نوبتی + AI + UI اصلی | ⏳ |
| ۵ | سیستم‌های متا | قهرمان/کارت/صندوق/فروشگاه/مأموریت/BP/آرنا/کلن | ⏳ |
| ۶ | گرافیک/صدا/انیمیشن/فارسی‌سازی | تجربه بصری و صوتی کامل | ⏳ |
| ۷ | بسته‌بندی APK و تست | APK قابل نصب + تست هواپیما/ری‌استارت/پایداری | ⏳ |
| ۸ | مستندات و بکاپ | راهنما + بکاپ/بازیابی | ⏳ |

**اولویت پیشنهادی:** ابتدا **نبرد آفلاین با AI** (قلب بازی)، سپس متا.

---

## ۱۴. تصمیم‌های موردنیاز کاربر

1. **نسخه هدف:** 3.4.2 (پیشنهادی، جدیدتر) یا 3.3.7؟
2. **معماری:** گزینه A (پچ کامل)، B (بازسازی)، یا C (هیبرید)؟
3. **دامنه اولیه:** فقط نبرد، یا کل سیستم‌های متا؟
4. **تبلیغات و IAP:** حذف کامل یا نسخه شبیه‌سازی‌شده؟
5. **موتور بازسازی:** Unity (سازگار با Assetها) یا Godot/Flutter؟
6. **ABI:** فقط arm64 یا armv7 هم؟
7. **زبان:** فارسی به‌عنوان زبان اصلی؟

---

## ۱۵. پیوست

### ۱۵.۱ فایل‌های تحلیلی تولیدشده
```
original/                          APKها + هش + متادیتا Bazaar
extracted/3.4.2/base/              بازشده base.apk
extracted/3.4.2/split/             بازشده split_config.arm64_v8a.apk
extracted/textassets/              78 TextAsset (Config/Localization)
extracted/inventory/               فهرست MonoScript/Texture/Audio/Animation
extracted/metadata/string_literals_clean.txt
extracted/metadata/string_table.txt
docs/01-technical-report.md        همین گزارش
```

### ۱۵.۲ آمار کلیدی
```
Unity: 6000.0.58f2
Scenes: 19
MonoScript: 3,784
Assembly-CSharp: 1,570
Texture2D: 704
Sprite: 4,457
AudioClip: 1,225
AnimationClip: 2,017
AnimatorController: 543
TextAsset: 78
Localization: 6,433 rows × 14 languages
Heroes: 40
Skins: 77
Chests: 18
Arenas: 13
BattlePass rewards: 36
TrophyRoad: 71 + 29 VIP + 4 Announcer
Tournaments: 2
Socket.IO events (MT_*): ~60
```

### ۱۵.۳ منابع عمومی
- `com.paeezanstudio.pesarkhande` — Paeezan Studio
- نسخه‌های عمومی: 3.4.2 (Bazaar)، 2.8.0 (APKPure)
- سرور: `android.pesarkhandeh.ir:443`
- Firebase: `pesarkhande-c6a7b`

---

> **جمع‌بندی:** بازی از نظر منابع و داده‌ها **بسیار غنی** و قابل بازسازی است. چالش اصلی، **منطق نبرد و پروتکل سرور** است. با داده‌های موجود می‌توان یک نسخه آفلاین با وفاداری بالا ساخت، به‌شرط آنکه رفتارهای بازسازی‌شده صریحاً «تقریبی» علامت‌گذاری شوند و با آزمون تأیید شوند.
>
> **منتظر تأیید گزارش و انتخاب مسیر (A/B/C) هستیم تا وارد مرحله ۲ شویم.**
