# Gamblit Promo Code Auto-Redeemer ⚡

Gamblit hesabının erişebildiği promo kodları, Gamblit'in Discord `#codes` kanalında yayınlandığı anda milisaniye düzeyinde algılayıp asenkron bağlantı havuzu ve sıfır-bloklama kuyruk mimarisiyle en düşük gecikmeyle redeem eden otomasyon sistemi.

---

## 🏗️ Mimari Şema

```text
                     ┌──────────────────┐
                     │ Gamblit Discord  │
                     │     #codes       │
                     └────────┬─────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │ Discord Listener │ (Zero-blocking on_message)
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Code Parser    │ (Regex & Heuristic < 1ms)
                    └────────┬─────────┘
                             │
                    ┌────────▼────────┐
                    │ Duplicate Check  │ (Layer 1: RAM set | Layer 2: SQLite)
                    └────────┬────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Async Queue    │ (asyncio.Queue)
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Redeem Worker   │ (Persistent Session / Connection Pool)
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Gamblit Client  │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Response Parser  │ (SUCCESS, EXPIRED, ALREADY_USED, 429, etc.)
                    └───────┬───┬──────┘
                            │   │
                 ┌──────────┘   └──────────┐
                 ▼                         ▼
          ┌──────────────┐          ┌──────────────┐
          │   Database   │          │   Metrics    │ (T0 -> T1 -> T2 -> T3)
          │  (aiosqlite) │          │  (Latency)   │
          └──────────────┘          └──────────────┘
```

---

## 🚀 Temel Özellikler

1. **Ultra Düşük Gecikme (Hot Path Optimizasyonu):**
   * Discord mesajı alındığı anda event loop bloklanmadan mikro-saniyeler içinde kod ayrıştırılır ve `asyncio.Queue`ya iletilir.
   * `aiohttp.ClientSession` bağlantı havuzu (TCP Keep-Alive, DNS cache) uygulama başlangıcında önceden ısıtılır (cold-start önlenir).
2. **Çift Katmanlı Duplicate Koruması:**
   * **RAM Set:** Bellek içinde $O(1)$ anında mükerrer kod filtreleme.
   * **SQLite (aiosqlite):** Yeniden başlatmalarda ve geçmiş kontrollerinde kalıcı veritabanı koruması.
3. **Detaylı Yanıt Ayrıştırma:**
   * `SUCCESS`, `INVALID_CODE`, `EXPIRED`, `ALREADY_USED`, `NOT_ELIGIBLE`, `RATE_LIMITED`, `AUTH_ERROR`, `SERVER_ERROR`, `NETWORK_ERROR`.
4. **Akıllı Retry ve Backoff:**
   * 429 Rate Limit durumunda sunucunun belirttiği `Retry-After` süresine riayet edilir.
   * Terminal durumlarda (geçersiz/süresi dolmuş/önceden kullanılmış) gereksiz yere istek tekrarlanmaz.
5. **Kapsamlı Gecikme Ölçümü (Latency Breakdown):**
   * $T_0$: Discord mesaj varışı
   * $T_1$: Parser tamamlanma
   * $T_2$: HTTP istek başlangıcı
   * $T_3$: HTTP yanıt varışı
   * Metrikler konsol, veritabanı ve `/status` komutu üzerinden raporlanır.
6. **Güvenlik ve Veri Maskeleme:**
   * Loglara `cf_clearance`, token, şifre veya oturum çerezi gibi hassas veriler sızdırılmaz (`SensitiveDataFilter`).
   * `.env` ve SQLite `.db` dosyaları varsayılan olarak `.gitignore` altındadır.
7. **Crash Recovery & Watchdog:**
   * Ani kapanmalarda yarıda kalan `PROCESSING` kodlar açılışta güvenli şekilde `UNKNOWN` durumuna taşınır.
   * `HealthMonitor` periyodik olarak Gamblit oturumunu denetler.

---

## 📁 Proje Dosya Yapısı

```text
.
├── app/
│   ├── __init__.py
│   ├── config.py              # .env ve parametre yönetimi
│   ├── discord_listener.py    # Discord botu & event dinleyici
│   ├── parser.py              # Yüksek hızlı promo kod regex motoru
│   ├── queue.py               # RAM Set + Async kuyruk yönetimi
│   ├── worker.py              # Arka plan HTTP redeem işlemcisi
│   ├── gamblit_client.py      # Persistent HTTP session & Cloudflare cookie yöneticisi
│   ├── models.py              # Veri modelleri, Enums ve Latency sınıfları
│   ├── database.py            # aiosqlite asenkron veritabanı
│   ├── metrics.py             # Milisaniye latency ve performans sayaçları
│   ├── logging_config.py      # Hassas veri maskeleme & rotasyonlu loglama
│   └── health.py              # Gamblit oturum ve sistem sağlık kontrolü
│
├── tests/
│   ├── __init__.py
│   ├── mock_gamblit.py        # Yerel aiohttp mock Gamblit test sunucusu
│   ├── test_parser.py         # Regex ve mesaj ayrıştırma testleri
│   ├── test_database.py       # Veritabanı ve crash recovery testleri
│   ├── test_worker.py         # Kuyruk ve worker testleri
│   └── test_redeem.py         # Mock Gamblit üzerinde uçtan uca HTTP testleri
│
├── scripts/
│   ├── setup.py               # İnteraktif konfigürasyon sihirbazı
│   └── migrate.py             # Veritabanı şema denetimi
│
├── data/                      # SQLite veritabanı dizini
├── logs/                      # Günlük log dosyaları
├── Dockerfile                 # Container imajı
├── docker-compose.yml         # Container dağıtımı
├── gamblit-redeemer.service   # Linux systemd servis şablonu
├── requirements.txt           # Python bağımlılıkları
├── .env.example               # Örnek ortam değişkenleri
├── .gitignore                 # Güvenlik ve çöp dosya filtresi
├── README.md                  # Proje dokümantasyonu
└── main.py                    # Ana uygulama başlatıcı
```

---

## ⚙️ Kurulum & Çalıştırma

### 1. Python Ortamı
Gereksinim: **Python 3.12+**

```bash
# Sanal ortam oluşturma
python -m venv .venv

# Ortamı aktif etme (Windows)
.\.venv\Scripts\activate

# Ortamı aktif etme (Linux/macOS)
source .venv/bin/activate

# Bağımlılıkları yükleme
pip install -r requirements.txt
```

### 2. Konfigürasyon (.env)
İnteraktif sihirbazı çalıştırabilirsiniz:
```bash
python scripts/setup.py
```
Veya `.env.example` dosyasını `.env` olarak kopyalayıp düzenleyin:
```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=123456789012345678
DISCORD_CHANNEL_ID=123456789012345678

GAMBLIT_BASE_URL=https://gamblit.net
# Tarayıcınızdan aldığınız çerezler (cf_clearance, _iidt, _vid_t vb.)
GAMBLIT_COOKIES={"cf_clearance":"...","_iidt":"...","_vid_t":"..."}
```

### 3. Gamblit Çerezlerini Alma (Cloudflare Session)
Gamblit Cloudflare JS challenge koruması altındadır:
1. Tarayıcınızda (Chrome/Firefox) `https://gamblit.net` adresine girip hesabınıza giriş yapın.
2. `F12` (Geliştirici Araçları) -> **Application** -> **Cookies** sekmesine gidin.
3. Özellikle `cf_clearance`, `_iidt`, `_vid_t` ve oturum çerezlerini kopyalayıp `.env` içerisindeki `GAMBLIT_COOKIES` alanına JSON formatında veya `k=v; k2=v2` formatında yapıştırın.

### 4. Oturumu Test Etme
Gerçek Gamblit oturumunuzun geçerli olduğunu doğrulamak için:
```bash
python main.py --test-auth
```

### 5. Botu Başlatma
```bash
python main.py
```

---

## 🧪 Testleri Çalıştırma

Mock sunucu üzerinden tüm durumlar canlı Gamblit hesabına dokunmadan test edilir:

```bash
pytest -v
```

Test kapsamı:
* `test_parser.py`: Kod etiketleri, backtick blokları, emojiler, linkler, geçersiz mesajlar.
* `test_database.py`: Duplicate engelleme, durum güncelleme, crash recovery.
* `test_worker.py`: Async kuyruk işleme, worker akışı, duplicate önleme.
* `test_redeem.py`: Mock sunucuyla 200 SUCCESS, 400 EXPIRED, 400 ALREADY_USED, 400 NOT_ELIGIBLE, 429 RATE_LIMITED, 500 SERVER_ERROR ve AUTH_ERROR testleri.

---

## 🖥️ Sunucu / VPS Dağıtımı

### Docker ile:
```bash
docker-compose up -d --build
```

### systemd ile (Ubuntu/Debian):
```bash
sudo cp gamblit-redeemer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gamblit-redeemer
sudo journalctl -u gamblit-redeemer -f
```
