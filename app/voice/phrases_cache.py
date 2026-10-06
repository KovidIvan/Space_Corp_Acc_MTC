"""Pre-rendered fixed phrase audio cache for low latency (SC-5 compliance)."""

from __future__ import annotations

import logging

from app.interfaces import TTS
from app.schemas import AgentConfig

logger = logging.getLogger(__name__)

# Standard fallback phrases when config items are empty
DEFAULT_PHRASES = {
    "greeting": "Здравствуйте! Это ИИ-ассистент компании. Меня зовут Иван. Чем могу помочь?",
    "disclosure": "Разговор записывается для контроля качества.",
    "closing": "Спасибо за обращение! Всего доброго!",
    "reask": "Извините, не совсем понял вас. Повторите, пожалуйста.",
    "hold": "Секунду, уточняю информацию...",
    "handoff": "Переключаю вас на руководителя. Пожалуйста, оставайтесь на линии.",
}


class PhrasesCache:
    """In-memory cache for pre-synthesized PCM16 audio phrases."""

    def __init__(self, tts: TTS) -> None:
        self.tts = tts
        self._cache: dict[str, bytes] = {}

    def preload(self, config: AgentConfig | None = None) -> None:
        """Pre-synthesize all scenario static phrases."""
        phrases = dict(DEFAULT_PHRASES)
        if config is not None:
            if config.greeting:
                phrases["greeting"] = config.greeting
            if config.disclosure:
                phrases["disclosure"] = config.disclosure
            if config.closing:
                phrases["closing"] = config.closing

        for key, text in phrases.items():
            try:
                self._cache[key] = self.tts.synth(text)
                logger.info("Pre-synthesized cached phrase: %s", key)
            except Exception as exc:
                logger.warning("Failed to pre-synthesize phrase '%s': %s", key, exc)
                self._cache[key] = b""

    def get(self, key: str, fallback_text: str = "") -> bytes:
        """Get pre-synthesized audio for *key*, or synthesize *fallback_text* on demand."""
        if key in self._cache and self._cache[key]:
            return self._cache[key]

        if fallback_text:
            return self.tts.synth(fallback_text)

        default_text = DEFAULT_PHRASES.get(key, "")
        return self.tts.synth(default_text) if default_text else b""
