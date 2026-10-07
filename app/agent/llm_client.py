"""Local LLM client adapter using Ollama-compatible HTTP API.

Satisfies the ``app.interfaces.LLM`` protocol.  All requests go through
``SafeHttpClient`` and stay on localhost (Ollama default ``http://127.0.0.1:11434``).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.core.safe_http import SafeHttpClient

logger = logging.getLogger(__name__)

# JSON schema for Ollama's structured output format option.
_OLLAMA_CHAT_PATH = "/api/chat"


class OllamaLLM:
    """Async LLM adapter backed by a local Ollama instance.

    Satisfies the ``app.interfaces.LLM`` protocol::

        async def json(self, system: str, user: str, schema: dict) -> dict: ...

    The adapter sends a chat completion request with ``format`` set to the
    caller-provided JSON schema so that Ollama constrains the output tokens.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        http: SafeHttpClient | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = (base_url or settings.llm_base_url).rstrip("/")
        self._model = model or settings.llm_model
        self._http = http or SafeHttpClient()
        self._timeout_s = timeout_s

    async def json(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a chat request and return parsed JSON matching *schema*.

        Args:
            system: System prompt describing the task.
            user: User message (e.g. the transcript).
            schema: JSON Schema object used as Ollama ``format``.

        Returns:
            Parsed JSON dictionary from the model response.

        Raises:
            RuntimeError: On network, parsing, or unexpected API errors.
        """
        url = f"{self._base_url}{_OLLAMA_CHAT_PATH}"
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "format": schema,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 1024,
            },
        }

        try:
            response = await self._http.request(
                "POST",
                url,
                json=payload,
                timeout=self._timeout_s,
            )
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError("LLM request failed") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Ollama returned HTTP {response.status_code}")

        try:
            body = response.json()
        except Exception as exc:
            raise RuntimeError("Ollama response is not valid JSON") from exc

        content = body.get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("Ollama response has no message content")

        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM output is not valid JSON") from exc

        if not isinstance(result, dict):
            raise TypeError("LLM output is not a JSON object")

        return result

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()
