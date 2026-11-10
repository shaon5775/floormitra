"""Settings: the Gemini key comes from the environment, a .env file, or Streamlit secrets (on Streamlit Cloud)."""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

DEFAULT_MODEL = "gemini-3.5-flash-lite"   # answered fastest on a free AI Studio key (checked Nov 2026)


def gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        try:
            import streamlit as st
            key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:  # noqa: BLE001 - no secrets file
            key = ""
    return key


def model_name() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def build(offline: bool, plant=None):
    """Return (agent, voice). Offline = rule-based brain + pretend voice, no network."""
    from .agent import FloorMitra, GeminiBrain, MockBrain
    from .manuals import Manuals
    from .plant import Plant
    from .voice import GeminiVoice, MockVoice

    plant = plant or Plant()
    if offline:
        return FloorMitra(MockBrain(plant), plant, Manuals()), MockVoice()
    key = gemini_key()
    return FloorMitra(GeminiBrain(key, model_name()), plant, Manuals()), GeminiVoice(key)


def write_text(prompt: str) -> str:
    """One plain Gemini call (used for the supervisor's shift report)."""
    from google import genai

    from .agent import _retry
    client = genai.Client(api_key=gemini_key())
    resp = _retry(lambda: client.models.generate_content(model=model_name(), contents=prompt))
    return (resp.text or "").strip()
