"""Tests for deterministic audio processing and local voice adapters."""

import numpy as np
import pytest

from app.voice.vad import FRAME_SAMPLES, VADSegmenter

FRAME_BYTES = FRAME_SAMPLES * 2


class FakeSpeechModel:
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = iter(probabilities)

    def speech_probability(self, pcm16: bytes, sample_rate: int) -> float:
        assert len(pcm16) == FRAME_BYTES
        assert sample_rate == 16_000
        return next(self.probabilities)


def frame(value: int) -> bytes:
    return np.full(FRAME_SAMPLES, value, dtype="<i2").tobytes()


def test_vad_ends_utterance_after_at_least_700ms_silence() -> None:
    speech_frames = [frame(100)] * 2
    silence_frames = [frame(0)] * 22
    detector = FakeSpeechModel([0.9] * 2 + [0.1] * 22)
    segmenter = VADSegmenter(detector)

    utterances = segmenter.feed(b"".join(speech_frames + silence_frames))

    assert utterances == [b"".join(speech_frames)]
    assert 21 * FRAME_SAMPLES < segmenter.minimum_silence_samples <= 22 * FRAME_SAMPLES


def test_vad_preserves_short_silence_inside_utterance() -> None:
    speech_a, short_silence, speech_b = frame(100), frame(0), frame(200)
    trailing_silence = [frame(0)] * 22
    detector = FakeSpeechModel([0.9, 0.1, 0.9] + [0.1] * 22)
    segmenter = VADSegmenter(detector, silence_duration_ms=700)

    utterances = segmenter.feed(speech_a + short_silence + speech_b + b"".join(trailing_silence))

    assert utterances == [speech_a + short_silence + speech_b]


def test_vad_flushes_partial_frame_and_unfinished_utterance() -> None:
    detector = FakeSpeechModel([0.9])
    segmenter = VADSegmenter(detector)
    partial_speech = frame(100)[:640]

    assert segmenter.feed(partial_speech) == []
    assert segmenter.flush() == [partial_speech]
    assert segmenter.flush() == []


def test_vad_rejects_odd_sized_pcm16_input() -> None:
    segmenter = VADSegmenter(FakeSpeechModel([]))

    with pytest.raises(ValueError, match="16-bit"):
        segmenter.feed(b"\x00")


def test_vad_only_accepts_16khz_audio() -> None:
    with pytest.raises(ValueError, match="16000 Hz"):
        VADSegmenter(FakeSpeechModel([]), sample_rate=8_000)
