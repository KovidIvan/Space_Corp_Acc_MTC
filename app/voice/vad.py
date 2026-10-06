"""Silero-based voice activity detection and deterministic endpointing."""

from collections.abc import Callable
from typing import Protocol

import numpy as np

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 512
FRAME_BYTES = FRAME_SAMPLES * 2


class SpeechProbabilityModel(Protocol):
    """Model that estimates speech probability for a 512-sample PCM frame."""

    def speech_probability(self, pcm16: bytes, sample_rate: int) -> float: ...


class SileroVAD:
    """Lazy wrapper around the packaged Silero VAD model."""

    def __init__(self, model: object | None = None) -> None:
        self._model = model

    def _load_model(self) -> object:
        try:
            import torch
            from silero_vad import load_silero_vad
        except ImportError as exc:
            raise RuntimeError("Install the optional voice dependencies to use Silero VAD") from exc
        self._torch = torch
        self._model = load_silero_vad(onnx=False)
        return self._model

    def speech_probability(self, pcm16: bytes, sample_rate: int = SAMPLE_RATE) -> float:
        """Return the Silero speech probability for a single PCM16 frame."""
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"Silero VAD expects {SAMPLE_RATE} Hz audio")
        if len(pcm16) != FRAME_BYTES:
            raise ValueError(f"Silero VAD expects {FRAME_SAMPLES} samples per frame")
        model = self._model if self._model is not None else self._load_model()
        torch = getattr(self, "_torch", None)
        if torch is None:
            try:
                import torch
            except ImportError as exc:
                raise RuntimeError("Install the optional voice dependencies to use Silero VAD") from exc
        audio = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio)
        with torch.inference_mode():
            result = model(tensor, sample_rate)
        if isinstance(result, tuple):
            result = result[0]
        probability = float(result.item() if hasattr(result, "item") else result)
        if not 0.0 <= probability <= 1.0:
            raise ValueError("VAD model returned a probability outside [0, 1]")
        return probability


class VADSegmenter:
    """Turn PCM16 input into utterances separated by a silence interval."""

    def __init__(
        self,
        model: SpeechProbabilityModel | Callable[[bytes, int], float],
        *,
        threshold: float = 0.5,
        silence_duration_ms: int = 700,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        if sample_rate != SAMPLE_RATE:
            raise ValueError(f"VAD segmentation expects {SAMPLE_RATE} Hz audio")
        if not 0.0 < threshold < 1.0:
            raise ValueError("threshold must be between 0 and 1")
        if silence_duration_ms <= 0:
            raise ValueError("silence_duration_ms must be positive")
        self.model = model
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.minimum_silence_samples = (sample_rate * silence_duration_ms + 999) // 1000
        self._frame_buffer = bytearray()
        self._speech_buffer = bytearray()
        self._silence_buffer = bytearray()
        self._silence_samples = 0
        self._speaking = False

    def feed(self, pcm16: bytes) -> list[bytes]:
        """Consume audio and return utterances ended by the configured silence."""
        if len(pcm16) % 2:
            raise ValueError("PCM16 audio must contain complete 16-bit samples")
        self._frame_buffer.extend(pcm16)
        utterances: list[bytes] = []
        while len(self._frame_buffer) >= FRAME_BYTES:
            frame = bytes(self._frame_buffer[:FRAME_BYTES])
            del self._frame_buffer[:FRAME_BYTES]
            utterance = self._process_frame(frame, FRAME_BYTES)
            if utterance is not None:
                utterances.append(utterance)
        return utterances

    def flush(self) -> list[bytes]:
        """Process a partial final frame and return any unfinished utterance."""
        if self._frame_buffer:
            valid_bytes = len(self._frame_buffer)
            frame = bytes(self._frame_buffer) + bytes(FRAME_BYTES - valid_bytes)
            self._frame_buffer.clear()
            utterance = self._process_frame(frame, valid_bytes)
            if utterance is not None:
                return [utterance]
        if not self._speaking:
            return []
        utterance = bytes(self._speech_buffer)
        self._reset_utterance()
        return [utterance] if utterance else []

    def reset(self) -> None:
        """Discard any buffered audio and endpoint state."""
        self._frame_buffer.clear()
        self._reset_utterance()

    def _probability(self, frame: bytes) -> float:
        if hasattr(self.model, "speech_probability"):
            return self.model.speech_probability(frame, self.sample_rate)
        return self.model(frame, self.sample_rate)

    def _process_frame(self, frame: bytes, valid_bytes: int) -> bytes | None:
        probability = self._probability(frame)
        if not 0.0 <= probability <= 1.0:
            raise ValueError("VAD model returned a probability outside [0, 1]")
        if probability >= self.threshold:
            if self._speaking:
                self._speech_buffer.extend(self._silence_buffer)
            self._silence_buffer.clear()
            self._silence_samples = 0
            self._speaking = True
            self._speech_buffer.extend(frame[:valid_bytes])
            return None
        if not self._speaking:
            return None
        self._silence_buffer.extend(frame[:valid_bytes])
        self._silence_samples += valid_bytes // 2
        if self._silence_samples < self.minimum_silence_samples:
            return None
        utterance = bytes(self._speech_buffer)
        self._reset_utterance()
        return utterance

    def _reset_utterance(self) -> None:
        self._speech_buffer.clear()
        self._silence_buffer.clear()
        self._silence_samples = 0
        self._speaking = False
