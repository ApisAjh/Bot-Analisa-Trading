"""Integrasi ke AI Vision API. Provider dipilih lewat env var AI_PROVIDER
(gemini | openai | claude), default "gemini".

Semua request memakai httpx.AsyncClient sekali pakai (no persistent session,
no disk cache). Gambar dikirim sebagai base64 langsung dalam request body dan
tidak pernah ditulis ke disk atau database.
"""

import base64
import os
from typing import Optional

import httpx

from .prompts import (
    IMAGE_ANALYSIS_SYSTEM_PROMPT,
    build_general_question_prompt,
    build_text_analysis_prompt,
)

AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").lower()
AI_API_KEY = os.environ.get("AI_API_KEY", "")

# Model default bisa dioverride lewat env var. Cek dokumentasi resmi masing-masing
# provider untuk nama model vision terbaru sebelum deploy production.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5")

TIMEOUT = httpx.Timeout(50.0, connect=10.0)
FALLBACK_ERROR = "⚠️ AI tidak mengembalikan hasil analisa yang valid. Coba lagi beberapa saat lagi."


async def analyze_chart_image(image_bytes: bytes, mime_type: str, caption: str = "") -> str:
    """Kirim screenshot chart ke provider AI Vision yang aktif dan kembalikan teks analisa."""
    user_note = f"\n\nCatatan tambahan dari user: {caption}" if caption else ""
    prompt = IMAGE_ANALYSIS_SYSTEM_PROMPT + user_note

    if AI_PROVIDER == "openai":
        return await _call_openai_vision(image_bytes, mime_type, prompt)
    if AI_PROVIDER == "claude":
        return await _call_claude_vision(image_bytes, mime_type, prompt)
    return await _call_gemini_vision(image_bytes, mime_type, prompt)


async def analyze_text_market(symbol: str, market_context: str) -> str:
    """Minta analisa teknikal berbasis data teks (untuk perintah /analyze)."""
    prompt = build_text_analysis_prompt(symbol, market_context)

    if AI_PROVIDER == "openai":
        return await _call_openai_text(prompt)
    if AI_PROVIDER == "claude":
        return await _call_claude_text(prompt)
    return await _call_gemini_text(prompt)


async def answer_general_question(question: str) -> str:
    """Jawab pertanyaan bebas via chat, tunduk pada AI ROLE (scope trading only,
    aturan probabilitas/risk warning, dan penolakan topik di luar trading)."""
    prompt = build_general_question_prompt(question)

    if AI_PROVIDER == "openai":
        return await _call_openai_text(prompt)
    if AI_PROVIDER == "claude":
        return await _call_claude_text(prompt)
    return await _call_gemini_text(prompt)


# ---------------------------------------------------------------------------
# Gemini Vision API
# ---------------------------------------------------------------------------

async def _call_gemini_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={AI_API_KEY}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64}},
                ]
            }
        ],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1200},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return _extract_gemini_text(data)


async def _call_gemini_text(prompt: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={AI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1000},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return _extract_gemini_text(data)


def _extract_gemini_text(data: dict) -> str:
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError):
        return FALLBACK_ERROR


# ---------------------------------------------------------------------------
# OpenAI Vision API
# ---------------------------------------------------------------------------

async def _call_openai_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                ],
            }
        ],
        "max_tokens": 1200,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return _extract_openai_text(data)


async def _call_openai_text(prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}"}
    payload = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return _extract_openai_text(data)


def _extract_openai_text(data: dict) -> str:
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return FALLBACK_ERROR


# ---------------------------------------------------------------------------
# Claude Vision API
# ---------------------------------------------------------------------------

async def _call_claude_vision(image_bytes: bytes, mime_type: str, prompt: str) -> str:
    b64 = base64.b64encode(image_bytes).decode()
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": AI_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1200,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return _extract_claude_text(data)


async def _call_claude_text(prompt: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": AI_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return _extract_claude_text(data)


def _extract_claude_text(data: dict) -> str:
    try:
        parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
        return "\n".join(parts).strip() or FALLBACK_ERROR
    except (KeyError, IndexError, TypeError):
        return FALLBACK_ERROR
