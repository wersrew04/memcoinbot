# Solana Mem Coin Auto Trading Bot

To‘liq ishlaydigan (scanner → filter → risk → buy → monitor/sell → Telegram) Solana memecoin boti.

## Nima ishlaydi

| Modul | Holat |
|-------|--------|
| DexScreener + Birdeye scanner | ✅ |
| Filter pipeline (liq, vol, MC, holders, top10, dev, mint/freeze, honeypot) | ✅ |
| Risk manager (max positions, daily loss, cooldown, Redis/memory) | ✅ |
| Jupiter buy (SOL → token) | ✅ |
| Position monitor (TP / SL / trailing stop) | ✅ |
| Jupiter sell | ✅ |
| Telegram start/stop/positions/status + trade notify | ✅ |
| Paper trading mode | ✅ (default) |
| Docker (bot + Redis + Postgres) | ✅ |

## Tezkor start

```bash
cd bot
cp .env.example .env
# .env ni to'ldiring

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Redis
docker compose up -d redis

# Paper mode da ishga tushirish (xavfsiz)
python main.py
```

### Docker to‘liq

```bash
docker compose up -d --build
```

## Muhim sozlamalar (`.env`)

| O‘zgaruvchi | Tavsif |
|-------------|--------|
| `PAPER_TRADING=true` | **Default.** Real tx yubormaydi. Test uchun. |
| `PAPER_TRADING=false` | Real savdo. Faqat kichik summa + alohida hot wallet. |
| `PRIVATE_KEY` | Phantom base58 private key (faqat live uchun) |
| `TRADE_AMOUNT_USD` | Har bir token uchun USD |
| `MAX_OPEN_POSITIONS` | Parallel ochiq pozitsiyalar |
| `STOP_LOSS_PCT` / `TAKE_PROFIT_PCT` / `TRAILING_STOP_PCT` | Chiqish strategiyasi |
| `MAX_DAILY_LOSS_USD` | Kunlik zarar limiti → bot auto-stop |
| `BIRDEYE_API_KEY` | Filterlar uchun kerak (security, holders) |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | Boshqaruv va bildirishnomalar |

## Oqim

```
Scanner (60s) → FilterPipeline → Risk pre-check → Jupiter BUY
                                                      ↓
                              PositionMonitor (15s) → TP/SL/Trail → Jupiter SELL
                                                      ↓
                                              Risk + Telegram notify
```

## Telegram buyruqlar

- `/start` yoki ▶️ Start – botni yoqish
- `/stop` – to‘xtatish
- `/positions` – ochiq pozitsiyalar
- `/status` – daily loss, running state
- `/stats` – qisqa statistika
- `/restart` – qayta ishga tushirish
- `/clean` yoki 🧹 Tozalash – ghost pozitsiyalar, cooldown, scanner cache + on-chain sinxron
- `/clean_all` – kuchli tozalash (+ kunlik zarar reset, tarix)

## Xavfsizlik ogohlantirishlari

1. **Memecoinlar ekstremal xavfli** – ko‘pchiligi nolga tushadi.
2. Avval `PAPER_TRADING=true` bilan kunlab test qiling.
3. Live uchun **alohida hot wallet**, kichik balans (masalan $50–100).
4. Private key `.env` da – hech qachon gitga commit qilmang.
5. Birdeye / Helius / Jupiter rate limit va ba’zi endpointlar pullik.
6. Bu loyiha ta’limiy maqsadda. Savdo o‘z xavfingiz ostida.

## Strukturа

```
bot/
├── config/          # settings + constants
├── scanner/         # DexScreener, Birdeye, new_pairs
├── filters/         # liquidity, volume, holders, security, pipeline
├── risk/            # RiskManager
├── buy/             # jupiter.py, executor.py
├── sell/            # monitor.py (TP/SL/trailing)
├── wallet/          # keypair, rpc
├── telegram/        # aiogram bot
├── utils/           # logger, retry, helpers
├── main.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## License

Educational / personal use. Trade at your own risk.

## Railway.com ga deploy qilish

1. GitHub/GitLab ga repo yuklang (`.env` ni **hech qachon** commit qilmang!).
2. [railway.app](https://railway.app) da yangi project → "Deploy from GitHub".
3. Root directory: `memebotcoin` (yoki papka nomi).
4. Variables (Settings → Variables) da quyidagilarni qo'shing:

```
PAPER_TRADING=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
BIRDEYE_API_KEY=...
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<kuchli-parol>
ADMIN_API_KEY=<random-string>
ADMIN_SESSION_SECRET=<random-string>
RPC_URL=https://api.mainnet-beta.solana.com
# ixtiyoriy: PRIVATE_KEY (faqat live uchun)
# DATABASE_URL va REDIS_URL – agar Railway Postgres/Redis qo'shsangiz avtomatik beriladi
```

5. **Port**: Kod `$PORT` ni o'qiydi (Railway avtomatik beradi). Admin panel ochiq URL da ishlaydi.
6. Deploy tugagach, Railway bergan public URL orqali `/` ga kiring → login.
7. Healthcheck: `/health`

### Tavsiyalar
- Avval `PAPER_TRADING=true` bilan ishga tushiring.
- Redis/Postgres qo'shish shart emas (in-memory + sqlite fallback bor).
- Agar Postgres qo'shsangiz: `DATABASE_URL` ni Railway bergan qiymatga o'zgartiring (`postgresql+asyncpg://...`).
- Telegram tokenni yangilang agar u ochiq repo ga tushgan bo'lsa.

## Xatoliklar tuzatildi (bu versiya)

- Railway `$PORT` ni to'g'ri o'qiydi (admin panel ochiladi).
- SQLite `data/` papkasi avtomatik yaratiladi.
- Redis/DB yo'q bo'lsa ham bot ishlaydi (fallback).
- `.dockerignore` qo'shildi (image kichikroq).
- `railway.toml` qo'shildi.
