"""Optional OpenAI-compatible speech transport; credentials remain server-side."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

import httpx

from .config import ConfigurationError, ENV_NAME, _url


@dataclass(frozen=True)
class SpeechEndpoint:
    base_url: str
    model: str
    key_env: str

    def key(self, env: Mapping[str, str]) -> str:
        key = env.get(self.key_env, "").strip()
        if not key:
            raise ConfigurationError(f"Speech API key is missing in {self.key_env}")
        return key


def speech_endpoint(kind: str, env: Mapping[str, str] | None = None) -> SpeechEndpoint | None:
    env = os.environ if env is None else env
    prefix = f"VOICE_{kind.upper()}_"
    base = env.get(prefix + "BASE_URL", "").strip()
    model = env.get(prefix + "MODEL", "").strip()
    if not base and not model:
        return None
    if not base or not model:
        raise ConfigurationError(f"{prefix}BASE_URL and {prefix}MODEL must both be set")
    key_env = env.get(prefix + "API_KEY_ENV", "VOICE_API_KEY")
    if not ENV_NAME.fullmatch(key_env):
        raise ConfigurationError(f"{prefix}API_KEY_ENV must name an environment variable")
    endpoint = SpeechEndpoint(_url(base), model, key_env)
    endpoint.key(env)
    return endpoint


class OpenAICompatibleVoice:
    def __init__(self, env: Mapping[str, str] | None = None):
        self.env = os.environ if env is None else env
        self.stt = speech_endpoint("stt", self.env)
        self.tts = speech_endpoint("tts", self.env)

    async def transcribe(self, content: bytes, *, filename: str = "speech.webm") -> str:
        if self.stt is None:
            raise ConfigurationError("Speech recognition is not configured")
        if not content or len(content) > 10_000_000:
            raise ValueError("Audio must be between 1 byte and 10 MB")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.stt.base_url + "/audio/transcriptions",
                headers={"Authorization": "Bearer " + self.stt.key(self.env)},
                data={"model": self.stt.model},
                files={"file": (filename, content)},
            )
            response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise ValueError("Speech provider returned no transcript")
        return result["text"]

    async def synthesize(self, text: str) -> bytes:
        if self.tts is None:
            raise ConfigurationError("Speech synthesis is not configured")
        if not text.strip() or len(text) > 4000:
            raise ValueError("Speech text must be 1–4000 characters")
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.tts.base_url + "/audio/speech",
                headers={"Authorization": "Bearer " + self.tts.key(self.env)},
                json={"model": self.tts.model, "input": text, "voice": self.env.get("VOICE_TTS_VOICE", "alloy"), "response_format": "mp3"},
            )
            response.raise_for_status()
            return response.content
