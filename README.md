# Trading AI Bot — Telegram AI Trading Analyzer

Bot Telegram yang menerima screenshot chart trading (TradingView, MT5, Binance,
Forex/Crypto/Stock) lalu menganalisanya lewat AI Vision API (Gemini / OpenAI /
Claude), dan bisa juga menganalisa symbol lewat perintah teks `/analyze`.

## Karakteristik arsitektur

- Python 3.12+, `python-telegram-bot` v21 (dipakai sebagai client Bot API, bukan
  Application/dispatcher — supaya cocok dengan model 1 invocation = 1 update).
- **Webhook only** — tidak ada `run_polling()` sama sekali.
- **Vercel Python Serverless Function** — `api/webhook.py` adalah
  `BaseHTTPRequestHandler`, gaya standar runtime `@vercel/python`. Tidak ada
  server yang hidup terus.
- **Tanpa database** — tidak ada SQLite/Postgres/Redis/file storage apa pun.
  Setiap request stateless.
- **Tanpa penyimpanan data/gambar user** — foto yang dikirim user diunduh
  langsung ke memory (`bytes`), dipakai sekali untuk request ke AI Vision API,
  lalu dibuang otomatis saat function selesai. Tidak pernah ditulis ke disk,
  tidak pernah dikirim ke storage pihak ketiga selain AI provider yang kamu
  pilih sendiri.
- Semua proses (ambil foto, panggil AI, ambil data market) terjadi **realtime**
  di dalam satu invocation, lewat HTTP call langsung (`httpx`) ke API terkait.

## Struktur project

```
trading-ai-bot/
├── api/
│   └── webhook.py        # entrypoint Vercel: POST /api/webhook
├── bot/
│   ├── __init__.py
│   ├── telegram.py       # parsing update + kirim balasan via Bot API
│   ├── ai_vision.py       # integrasi Gemini/OpenAI/Claude Vision
│   ├── market.py          # ambil data market (Binance/Twelve Data)
│   └── prompts.py         # template prompt & pesan bot
├── requirements.txt
├── vercel.json
├── .env.example
└── README.md
```

## 1. Siapkan Bot Telegram

1. Chat [@BotFather](https://t.me/BotFather) di Telegram, `/newbot`, ikuti
   instruksinya, catat **token** yang diberikan.

## 2. Siapkan API key AI Vision

Pilih salah satu provider (isi `AI_PROVIDER` sesuai pilihan):

| Provider | `AI_PROVIDER` | Dapatkan API key di |
|---|---|---|
| Gemini Vision | `gemini` | Google AI Studio |
| OpenAI Vision | `openai` | platform.openai.com |
| Claude Vision | `claude` | console.anthropic.com |

Default project ini `gemini` (model `gemini-2.0-flash`). Cek dokumentasi resmi
tiap provider untuk nama model vision terbaru sebelum production — nama model
bisa berubah seiring waktu, dan bisa dioverride lewat env var
`GEMINI_MODEL` / `OPENAI_MODEL` / `CLAUDE_MODEL`.

## 3. (Opsional) API key data market

Untuk pair **crypto** (mis. `BTCUSDT`), bot otomatis pakai **Binance public
API** — tidak butuh key apa pun.

Untuk pair **Forex/Stock** (mis. `XAUUSD`, `EURUSD`, `AAPL`), isi
`MARKET_API_KEY` dengan API key dari **Twelve Data** (twelvedata.com, ada free
tier). Jika kosong, `/analyze` untuk pair non-crypto akan tetap jalan tapi AI
hanya memberi analisa umum tanpa data harga presisi.

> Ingin pakai Alpha Vantage sebagai pengganti/tambahan? Tinggal tambahkan
> fungsi `_fetch_alphavantage()` di `bot/market.py` mengikuti pola
> `_fetch_twelvedata()`, lalu panggil di `fetch_market_snapshot()`.

## 4. Deploy ke Vercel

```bash
npm i -g vercel   # jika belum ada Vercel CLI

cd trading-ai-bot
vercel login
vercel            # deploy pertama (ikuti prompt, pilih project baru)
```

Vercel otomatis mendeteksi `requirements.txt` dan menjalankan
`api/webhook.py` sebagai Python Serverless Function.

## 5. Set Environment Variables di Vercel

Lewat dashboard (**Project → Settings → Environment Variables**) atau CLI:

```bash
vercel env add TELEGRAM_BOT_TOKEN
vercel env add AI_PROVIDER
vercel env add AI_API_KEY
vercel env add MARKET_API_KEY          # opsional
vercel env add TELEGRAM_WEBHOOK_SECRET  # opsional tapi disarankan
```

Setelah menambah env var, deploy ulang ke production:

```bash
vercel --prod
```

Catat URL production yang diberikan, misalnya:
`https://trading-ai-bot.vercel.app`

## 6. Pasang Webhook Telegram

Jalankan (ganti `<BOT_TOKEN>`, `<VERCEL_URL>`, dan `<WEBHOOK_SECRET>` — hilangkan
parameter `secret_token` jika kamu tidak set `TELEGRAM_WEBHOOK_SECRET`):

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
        "url": "https://<VERCEL_URL>/api/webhook",
        "secret_token": "<WEBHOOK_SECRET>",
        "allowed_updates": ["message", "edited_message"]
      }'
```

Cek status webhook:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

Response `"url"` harus menunjuk ke `https://<VERCEL_URL>/api/webhook` dan
`"last_error_message"` idealnya kosong.

## 7. Testing

- Buka chat dengan bot kamu di Telegram, kirim `/start`.
- Kirim `/analyze XAUUSD` atau `/analyze BTCUSDT`.
- Kirim screenshot chart (TradingView/MT5/Binance) — tunggu beberapa detik,
  bot akan membalas dengan format analisa lengkap.

Cek `https://<VERCEL_URL>/api/webhook` lewat browser (GET) untuk health check
cepat — harus mengembalikan JSON `{"ok": true, ...}`.

## Catatan teknis & batasan

- **Timeout**: `vercel.json` sudah set `maxDuration: 60` detik untuk
  mengakomodasi latency AI Vision API. Di paket Hobby Vercel, batas maksimum
  function duration mengikuti limit plan kamu — cek dashboard Vercel jika
  butuh durasi lebih panjang.
- **Ukuran gambar**: Telegram membatasi ukuran foto yang dikirim; tidak ada
  resize tambahan di bot ini. Untuk chart hasil screenshot biasa, ukurannya
  umumnya jauh di bawah limit.
- **Bukan financial advice**: seluruh hasil analisa AI bersifat edukatif,
  seperti yang selalu ditegaskan di bagian disclaimer setiap balasan bot.
- **Skalabilitas**: karena stateless dan tanpa DB, bot ini scale otomatis
  mengikuti model serverless Vercel — tidak ada rate limiting bawaan, jadi
  pertimbangkan menambahkan proteksi (mis. `TELEGRAM_WEBHOOK_SECRET`, atau
  rate limit di level provider AI) jika bot dipakai publik dalam skala besar.
