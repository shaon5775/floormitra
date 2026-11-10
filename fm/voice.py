"""Voice in, voice out with Gemini: workers keep their hands on the job.

    listen(audio) -> {"text": what the worker said (own script), "language": "bn"}
    speak(text)   -> WAV bytes, or None if speech is unavailable (the text answer is always shown)
"""
from __future__ import annotations

import io
import json
import os
import re
import wave

from .agent import _retry
from .lang import NAMES

LISTEN_MODEL = os.getenv("GEMINI_LISTEN_MODEL", "gemini-3.5-flash-lite")
SPEAK_MODEL = os.getenv("GEMINI_SPEAK_MODEL", "gemini-3.8-flash-lite-tts")
SPEAK_VOICE = os.getenv("GEMINI_SPEAK_VOICE", "Kore")

LISTEN_PROMPT = """Write down exactly what this factory worker says, word for word. Do not translate, do not answer.
There may be machine noise in the background; ignore it.
Use the NATIVE SCRIPT of the language spoken: Bengali -> বাংলা লিপি, Hindi -> देवनागरी (other Indian languages in
their own script). Only English, Hinglish or Banglish may be written in Latin letters. Machine words, alarm codes
and part numbers (E-205, SB-1250, lathe, compressor) may stay in Latin letters.
Write the letters themselves - NEVER \\u escape codes.
{hint}Return ONLY JSON: {{"text": "...", "language": "<ISO 639-1 code, or hinglish, or banglish>"}}"""


def parse_heard(raw: str) -> dict:
    """Read the listen reply leniently (Gemini sometimes breaks a \\u escape in Indian text)."""
    raw = raw or "{}"
    try:
        out = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        return {"text": str(out.get("text", "")).strip(), "language": str(out.get("language", "")).strip().lower()}
    except (AttributeError, json.JSONDecodeError):
        pass
    m = re.search(r'"text"\s*:\s*"(.*)"\s*,\s*"language"\s*:\s*"([^"]*)"', raw, re.S)
    if not m:
        return {"text": raw.strip(), "language": ""}
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda g: chr(int(g.group(1), 16)), m.group(1))
    text = re.sub(r"\\u[0-9a-fA-F]{0,3}", "", text).replace('\\"', '"').replace("\\n", " ")
    return {"text": re.sub(r"\s+", " ", text).strip(), "language": m.group(2).strip().lower()}


def pcm_to_wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def speakable(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_#`>|]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class GeminiVoice:
    def __init__(self, api_key: str):
        from google import genai
        from google.genai import types

        self.t = types
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=90_000, retry_options=types.HttpRetryOptions(attempts=2)))

    def listen(self, audio: bytes, mime_type: str = "audio/wav", language_hint: str = "") -> dict:
        t = self.t
        hint = f"The worker is expected to speak {NAMES.get(language_hint, language_hint)}.\n" if language_hint else ""
        resp = _retry(lambda: self.client.models.generate_content(
            model=LISTEN_MODEL,
            contents=[t.Part.from_bytes(data=audio, mime_type=mime_type), LISTEN_PROMPT.format(hint=hint)],
            config=t.GenerateContentConfig(temperature=0, response_mime_type="application/json")))
        return parse_heard(resp.text or "{}")

    def speak(self, text: str) -> bytes | None:
        t = self.t
        try:
            resp = _retry(lambda: self.client.models.generate_content(
                model=SPEAK_MODEL, contents=speakable(text),
                config=t.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=t.SpeechConfig(voice_config=t.VoiceConfig(
                        prebuilt_voice_config=t.PrebuiltVoiceConfig(voice_name=SPEAK_VOICE))))))
            part = resp.candidates[0].content.parts[0]
            mime = (part.inline_data.mime_type or "").lower()
            rate = int(re.search(r"rate=(\d+)", mime).group(1)) if "rate=" in mime else 24000
            data = part.inline_data.data
            return data if mime.startswith("audio/wav") else pcm_to_wav(data, rate)
        except Exception as e:  # noqa: BLE001 - speech is a bonus
            print(f"  (speech unavailable: {str(e)[:160]})")
            return None


class MockVoice:
    def listen(self, audio: bytes, mime_type: str = "audio/wav", language_hint: str = "") -> dict:
        return {"text": "দুই নম্বর লেদ মেশিনে E-205 দেখাচ্ছে, কী করব?", "language": "bn"}

    def speak(self, text: str) -> bytes | None:
        return pcm_to_wav(b"\x00\x00" * 2400)
