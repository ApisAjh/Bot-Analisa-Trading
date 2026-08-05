"""Ambil snapshot data market realtime untuk perintah /analyze <SYMBOL>.

Tidak ada data yang disimpan (no database/cache) — setiap request memanggil
API eksternal secara langsung dan hasilnya hanya dipakai sekali untuk
membentuk prompt ke AI, lalu dibuang begitu response dikirim.

Sumber data:
- Binance public API -> untuk pair crypto (mis. BTCUSDT, ETHUSDT)
- Twelve Data API -> untuk Forex/Stock (mis. XAUUSD, EURUSD, AAPL)
  (butuh MARKET_API_KEY; bisa juga diganti Alpha Vantage dengan menambah
  fungsi _fetch_alphavantage mengikuti pola yang sama)
"""

import os
import re
from typing import Optional

import httpx

MARKET_API_KEY = os.environ.get("MARKET_API_KEY", "")
TIMEOUT = httpx.Timeout(15.0, connect=5.0)

CRYPTO_HINT = re.compile(r"(USDT|BUSD|USDC|BTC|ETH|BNB)$", re.IGNORECASE)


def _normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace("/", "").replace(" ", "")


async def fetch_market_snapshot(symbol: str) -> str:
    """Kembalikan ringkasan data market (plain text) untuk symbol yang diminta.

    Mencoba Binance dulu untuk symbol yang polanya terlihat seperti crypto,
    lalu fallback ke Twelve Data (Forex/Stock), lalu coba Binance lagi
    sebagai upaya terakhir. Jika semua gagal, kembalikan pesan fallback
    agar AI tetap bisa memberi analisa umum.
    """
    symbol = _normalize_symbol(symbol)

    if CRYPTO_HINT.search(symbol):
        snapshot = await _fetch_binance(symbol)
        if snapshot:
            return snapshot

    snapshot = await _fetch_twelvedata(symbol)
    if snapshot:
        return snapshot

    snapshot = await _fetch_binance(symbol)
    if snapshot:
        return snapshot

    return (
        f"Data harga realtime untuk {symbol} tidak berhasil diambil dari API saat ini. "
        f"Berikan analisa umum berbasis pengetahuan pasar terkini untuk instrumen ini, "
        f"dan tegaskan bahwa data harga presisi tidak tersedia."
    )


async def _fetch_binance(symbol: str) -> Optional[str]:
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            d = resp.json()
        if "lastPrice" not in d:
            return None
        return (
            f"Symbol: {symbol} (sumber: Binance)\n"
            f"Harga terakhir: {d.get('lastPrice')}\n"
            f"Perubahan 24 jam: {d.get('priceChangePercent')}%\n"
            f"Tertinggi 24 jam: {d.get('highPrice')}\n"
            f"Terendah 24 jam: {d.get('lowPrice')}\n"
            f"Volume 24 jam: {d.get('volume')}"
        )
    except (httpx.HTTPError, ValueError, KeyError):
        return None


async def _fetch_twelvedata(symbol: str) -> Optional[str]:
    if not MARKET_API_KEY:
        return None
    url = f"https://api.twelvedata.com/quote?symbol={symbol}&apikey={MARKET_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            d = resp.json()
        if d.get("status") == "error" or "close" not in d:
            return None
        return (
            f"Symbol: {d.get('symbol', symbol)} (sumber: Twelve Data)\n"
            f"Harga penutupan terakhir: {d.get('close')}\n"
            f"Open: {d.get('open')}  High: {d.get('high')}  Low: {d.get('low')}\n"
            f"Perubahan: {d.get('change')} ({d.get('percent_change')}%)"
        )
    except (httpx.HTTPError, ValueError, KeyError):
        return None
