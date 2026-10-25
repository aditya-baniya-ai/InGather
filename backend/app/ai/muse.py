"""Thin wrapper around the Meta Model API (OpenAI-compatible). Backend only; the key never leaves this process."""

import base64
import json
from dataclasses import dataclass

import httpx
from openai import OpenAI

from app.config import Settings


class MuseUnavailable(RuntimeError):
    """Raised when an AI feature is used without MODEL_API_KEY."""


@dataclass
class GeneratedImage:
    data: bytes
    fmt: str  # webp|png|jpeg


class MuseClient:
    def __init__(self, settings: Settings, openai_client: OpenAI | None = None):
        self.settings = settings
        self._client = openai_client
        if self._client is None and settings.ai_live:
            self._client = OpenAI(
                base_url=settings.meta_model_base_url,
                api_key=settings.model_api_key,
                timeout=settings.meta_model_timeout_seconds,
                max_retries=3,  # transient network drops are retried with backoff
            )

    @property
    def ai_live(self) -> bool:
        return self._client is not None

    def _require(self) -> OpenAI:
        if self._client is None:
            raise MuseUnavailable("ai_unavailable")
        return self._client

    @property
    def responses(self):
        """Muse Spark Responses API (`.create(...)`), so the agent loop can take this or a fake."""
        return self._require().responses

    def generate_image(self, prompt: str) -> GeneratedImage:
        res = self._require().images.generate(
            model=self.settings.meta_image_model,
            prompt=prompt,
            n=1,
            size="1536x1024",
            extra_body={
                "output_format": "webp",
                "reasoning_strength": "low",
                # Built-in image search lets it match what the real city and venue types look like.
                "tool_enablement": {"enable_image_search": True, "enable_web_search": True, "enable_shell": False},
            },
        )
        fmt = (getattr(res, "output_format", None) or "webp").lower()
        return GeneratedImage(base64.b64decode(res.data[0].b64_json), "jpeg" if fmt == "jpg" else fmt)

    def transcribe_wav(self, audio: bytes) -> str:
        self._require()
        req = {"model": self.settings.meta_voice_model, "audioEncoding": "WAV", "mode": "PUSH_TO_TALK"}
        r = httpx.post(
            f"{self.settings.meta_model_base_url.rstrip('/')}/asr/transcribe",
            headers={"Authorization": f"Bearer {self.settings.model_api_key}", "Accept": "application/json"},
            files={"request": (None, json.dumps(req), "application/json"), "audio": ("audio.wav", audio, "audio/wav")},
            timeout=self.settings.meta_model_timeout_seconds,
        )
        r.raise_for_status()
        return (r.json().get("transcript") or "").strip()
