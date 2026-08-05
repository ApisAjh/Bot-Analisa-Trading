"""Vercel Python Serverless Function.

Endpoint: POST /api/webhook
Menerima Update dari Telegram Bot API (webhook mode), memprosesnya sekali,
lalu mengembalikan 200 OK. Tidak ada server yang berjalan terus-menerus,
tidak ada polling, tidak ada background process/scheduler, dan tidak ada
database/cache — cocok dengan model eksekusi serverless Vercel.
"""

import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# Pastikan package `bot/` (sejajar dengan folder `api/`) bisa di-import.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.telegram import process_update  # noqa: E402

# Opsional tapi direkomendasikan: set TELEGRAM_WEBHOOK_SECRET dan pasang
# secret_token yang sama saat memanggil setWebhook, supaya endpoint ini
# hanya menerima request yang benar-benar berasal dari Telegram.
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if WEBHOOK_SECRET:
            received = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if received != WEBHOOK_SECRET:
                self._send(401, {"ok": False, "error": "unauthorized"})
                return

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw_body = self.rfile.read(length) if length else b"{}"
            update = json.loads(raw_body or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"ok": False, "error": "invalid json"})
            return

        try:
            asyncio.run(process_update(update))
        except Exception as exc:  # noqa: BLE001
            # Tetap balas 200 ke Telegram supaya tidak retry berulang;
            # error dicatat ke stderr (muncul di Vercel function logs).
            print(f"[webhook error] {exc}", file=sys.stderr)

        self._send(200, {"ok": True})

    def do_GET(self):
        # Health check sederhana, berguna untuk cek deployment tanpa Telegram.
        self._send(200, {"ok": True, "service": "trading-ai-bot", "status": "running"})

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
