"""Text-to-speech adapter backed by local Silero or Piper TTS engines.

Outputs mono PCM16 (little-endian int16) at 16 kHz. Satisfies the ``app.interfaces.TTS`` protocol.
"""

from __future__ import annotations

import io
import logging
import wave
from pathlib import Path
from typing import Any

from app.interfaces import TTS

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


class LocalTTS(TTS):
    """Local text-to-speech adapter.

    Tries Piper TTS first, then Silero TTS, and falls back to a simple tone generator
    if optional voice dependencies are absent (enabling offline testing without audio hardware).
    """

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        engine: str = "auto",
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self.sample_rate = sample_rate
        self.engine = engine
        self._piper_voice: Any | None = None
        self._silero_model: Any | None = None

        if model_path and Path(model_path).exists():
            self._load_engine(Path(model_path))

    def _load_engine(self, path: Path) -> None:
        """Load local Piper or Silero model weights from disk."""
        if path.suffix == ".onnx":
            try:
                from piper import PiperVoice

                self._piper_voice = PiperVoice.load(str(path))
                self.engine = "piper"
                logger.info("Loaded Piper TTS model from %s", path)
                return
            except ImportError:
                logger.warning("Piper not installed, checking Silero")

        if path.is_dir() or path.suffix in {".pt", ".onnx"}:
            try:
                import torch

                self._silero_model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-models",
                    model="silero_tts",
                    language="ru",
                    speaker="v4_ru",
                    onnx=False,
                    trust_repo=True,
                )
                self.engine = "silero"
                logger.info("Loaded Silero TTS model")
                return
            except (ImportError, OSError, RuntimeError, ValueError):
                logger.warning("Failed to load Silero model")

        self.engine = "fallback"

    def synth(self, text: str) -> bytes:
        """Synthesize *text* into mono 16 kHz PCM16 audio bytes."""
        if not text.strip():
            return b""

        if self._piper_voice is not None:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav_file:
                self._piper_voice.synthesize(text, wav_file)
            wav_bytes = buf.getvalue()
            return self._extract_pcm16_from_wav(wav_bytes)

        if self._silero_model is not None:
            try:
                audio_tensor = self._silero_model.apply_tts(
                    text=text,
                    speaker="kseniya",
                    sample_rate=self.sample_rate,
                )
                audio_np = (audio_tensor.numpy() * 32767).astype("<i2")
                return audio_np.tobytes()
            except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
                logger.error("Silero synthesis failed")

        # Fallback for deterministic testing without voice models: return silent PCM padding matching text length
        num_samples = int(self.sample_rate * min(len(text) * 0.05, 3.0))
        return b"\x00\x00" * num_samples

    def _extract_pcm16_from_wav(self, wav_bytes: bytes) -> bytes:
        """Strip WAV header and return raw PCM samples."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            return wav_file.readframes(wav_file.getnframes())
