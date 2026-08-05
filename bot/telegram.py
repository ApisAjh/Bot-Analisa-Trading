"""Logika bot Telegram. Tidak pakai Application/polling — cukup `telegram.Bot`
(python-telegram-bot v21) untuk memanggil Bot API, karena setiap invocation di
Vercel hanya perlu memproses SATU update lalu selesai (stateless, webhook-only).

Tidak ada data atau gambar user yang ditulis ke disk/database: file foto
diunduh langsung ke memory (bytes) dan dibuang begitu response terkirim.
"""

import os

from telegram import Bot
from telegram.constants import ChatAction

from .ai_vision import analyze_chart_image, analyze_text_market, answer_general_question
from .market import fetch_market_snapshot
from .prompts import HELP_MESSAGE, WELCOME_MESSAGE

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


async def process_update(update: dict) -> None:
    """Proses satu Telegram Update (dict hasil json.loads dari request body)."""
    message = update.get("message") or update.get("edited_message")
    if not message:
        # Update jenis lain (callback_query, channel_post, dll) diabaikan.
        return

    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    caption = (message.get("caption") or "").strip()
    photos = message.get("photo")

    async with Bot(token=BOT_TOKEN) as bot:
        try:
            if text.startswith("/start"):
                await bot.send_message(chat_id=chat_id, text=WELCOME_MESSAGE)
            elif text.startswith("/help"):
                await bot.send_message(chat_id=chat_id, text=HELP_MESSAGE)
            elif text.startswith("/analyze"):
                await _handle_analyze_command(bot, chat_id, text)
            elif photos:
                await _handle_photo(bot, chat_id, photos, caption)
            elif text.startswith("/"):
                # command lain yang tidak dikenal
                await bot.send_message(
                    chat_id=chat_id,
                    text="Perintah tidak dikenali. Ketik /help untuk daftar perintah yang tersedia.",
                )
            elif text:
                await _handle_general_question(bot, chat_id, text)
            # jika tidak ada text/photo (misal sticker, voice note, dll) -> diamkan
        except Exception as exc:  # noqa: BLE001
            await bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Terjadi kesalahan saat memproses permintaan: {exc}",
            )


async def _handle_analyze_command(bot: Bot, chat_id: int, text: str) -> None:
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await bot.send_message(
            chat_id=chat_id,
            text="Format salah. Gunakan: /analyze <SYMBOL>\nContoh: /analyze XAUUSD",
        )
        return

    symbol = parts[1].strip()
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    market_context = await fetch_market_snapshot(symbol)
    result_text = await analyze_text_market(symbol, market_context)

    await bot.send_message(chat_id=chat_id, text=result_text)


async def _handle_general_question(bot: Bot, chat_id: int, text: str) -> None:
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    result_text = await answer_general_question(text)
    await bot.send_message(chat_id=chat_id, text=result_text)


async def _handle_photo(bot: Bot, chat_id: int, photos: list, caption: str) -> None:
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # Telegram mengirim beberapa resolusi; ambil yang paling besar untuk akurasi analisa.
    largest = max(photos, key=lambda p: p.get("file_size") or p.get("width", 0))
    file_id = largest["file_id"]

    tg_file = await bot.get_file(file_id)
    image_bytes = bytes(await tg_file.download_as_bytearray())  # langsung ke memory

    result_text = await analyze_chart_image(image_bytes, "image/jpeg", caption)

    await bot.send_message(chat_id=chat_id, text=result_text)
    # image_bytes keluar dari scope di sini dan tidak pernah disimpan ke mana pun.
