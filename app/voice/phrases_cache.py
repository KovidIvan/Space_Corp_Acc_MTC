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


def opening_phrases(config: AgentConfig | None = None) -> tuple[str, str]:
    """Return configured opening phrases with the mandatory identity and disclosure details."""
    greeting = config.greeting.strip() if config and config.greeting.strip() else DEFAULT_PHRASES["greeting"]
    disclosure = (
        config.disclosure.strip()
        if config and config.disclosure.strip()
        else DEFAULT_PHRASES["disclosure"]
    )

    owner_name = config.owner.name.strip() if config else "Иван"
    company = config.owner.company.strip() if config else ""
    owner_name = owner_name or "Иван"
    if owner_name.casefold() not in greeting.casefold():
        greeting = f"{greeting.rstrip('. ')}. Меня зовут {owner_name}."
    if company and company.casefold() not in greeting.casefold():
        greeting = f"{greeting.rstrip('. ')}. Вы позвонили в компанию {company}."

    opening = f"{greeting} {disclosure}".casefold()
    if "ии" not in opening and "искусствен" not in opening:
        disclosure = f"Я ИИ-ассистент. {disclosure}"
    if "запис" not in opening:
        disclosure = f"{disclosure.rstrip('. ')}. Разговор записывается."
    if "обрабатыва" not in opening:
        disclosure = f"{disclosure.rstrip('. ')}. Разговор обрабатывается локально."

    return greeting, disclosure


class PhrasesCache:
    """In-memory cache for pre-synthesized PCM16 audio phrases."""

    def __init__(self, tts: TTS) -> None:
        self.tts = tts
        self._cache: dict[str, bytes] = {}

    def preload(self, config: AgentConfig | None = None) -> None:
        """Pre-synthesize all scenario static phrases."""
        phrases = dict(DEFAULT_PHRASES)
        if config is not None:
            phrases["greeting"], phrases["disclosure"] = opening_phrases(config)
            if config.closing:
                phrases["closing"] = config.closing

        for key, text in phrases.items():
            try:
                self._cache[key] = self.tts.synth(text)
                logger.info("Pre-synthesized cached phrase: %s", key)
            except (RuntimeError, ValueError, OSError, ImportError):
                logger.warning("Failed to pre-synthesize phrase '%s'", key)
                self._cache[key] = b""

    def get(self, key: str, fallback_text: str = "") -> bytes:
        """Get pre-synthesized audio for *key*, or synthesize *fallback_text* on demand."""
        cached = self._cache.get(key)
        if cached:
            return cached

        if fallback_text:
            return self.tts.synth(fallback_text)

        default_text = DEFAULT_PHRASES.get(key, "")
        return self.tts.synth(default_text) if default_text else b""
