"""Local faster-whisper speech-to-text adapter.

Audio is expected as mono PCM16 (little-endian int16) at 16 kHz. Voice activity detection
runs upstream in ``app/voice/vad.py``, so the internal VAD filter of faster-whisper is off.
The model is always loaded from an explicit local directory and never downloaded.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from app.interfaces import Transcript, Word

SAMPLE_RATE = 16_000


def pcm16_to_float32(pcm16: bytes) -> np.ndarray:
    """Convert little-endian int16 PCM bytes to a float32 array scaled to [-1.0, 1.0]."""
    return np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0


def _load_model(model_path: Path, device: str, compute_type: str) -> Any:
    """Load a faster-whisper model from a local directory.

    The directory is checked before the package is imported, and only the directory path is
    passed on, so faster-whisper can never try to fetch a model by name.
    """
    if not model_path.is_dir():
        raise FileNotFoundError(
            f"Whisper model directory not found: {model_path}. "
            "Download the model first (make setup-voice) and pass its local path."
        )
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("install optional voice dependencies") from exc
    return WhisperModel(str(model_path), device=device, compute_type=compute_type)


class FasterWhisperSTT:
    """Speech-to-text adapter backed by a local faster-whisper model.

    Satisfies the ``app.interfaces.STT`` protocol.
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        model: Any | None = None,
        language: str = "ru",
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        """Create the adapter.

        Args:
            model_path: Local directory with a converted faster-whisper model. Ignored when
                ``model`` is injected.
            model: Already initialized model object, mainly for tests.
            language: Language code passed to the recognizer.
            device: Inference device, for example ``"cpu"`` or ``"cuda"``.
            compute_type: faster-whisper compute type, for example ``"int8"``.

        Raises:
            ValueError: If neither ``model`` nor ``model_path`` is given.
            FileNotFoundError: If ``model_path`` is not an existing directory.
            RuntimeError: If the optional voice dependencies are not installed.
        """
        if model is None:
            if model_path is None:
                raise ValueError("model_path is required when no model is injected")
            model = _load_model(Path(model_path), device, compute_type)
        self._model = model
        self._language = language

    def transcribe(self, pcm16: bytes, sample_rate: int) -> Transcript:
        """Recognize one utterance.

        Args:
            pcm16: Mono little-endian int16 PCM audio.
            sample_rate: Sample rate of the audio, must be 16000.

        Returns:
            Transcript with the joined text and per-word probabilities. Empty input gives
            an empty Transcript.

        Raises:
            ValueError: If the sample rate is not 16 kHz or the byte length is odd.
        """
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"expected {SAMPLE_RATE} Hz audio, got {sample_rate} Hz")
        if len(pcm16) % 2:
            raise ValueError("PCM16 input must contain an even number of bytes")
        if not pcm16:
            return Transcript()

        audio = pcm16_to_float32(pcm16)
        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            word_timestamps=True,
            vad_filter=False,
        )

        texts: list[str] = []
        words: list[Word] = []
        for segment in segments:
            text = (segment.text or "").strip()
            if text:
                texts.append(text)
            for item in getattr(segment, "words", None) or ():
                word = str(item.word).strip()
                if word:
                    words.append(Word(w=word, p=float(item.probability)))
        return Transcript(text=" ".join(texts), words=tuple(words))