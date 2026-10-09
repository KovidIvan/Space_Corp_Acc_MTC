"""Call session managing live audio streaming, VAD, STT, NLU, dialog and TTS over WebSocket.

Architecture (§4 Call flow, contracts/ws_protocol.md v1):
- PCM16 16 kHz mono little-endian audio streaming
- Endpointing via Silero VAD (700 ms silence)
- STT transcription with faster-whisper (word confidence)
- Turn understanding (NLU JSON + fallback) & routing
- Dialogue state machine (slot filling, max 8 turns, max 2 re-asks)
- Pre-rendered phrase cache for greeting & disclosure (zero initial latency)
- Call completion: CallResult creation, encryption, audit, and Telegram notification
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from httpx import HTTPError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.dialog import DialogSession, DialogState
from app.agent.llm_client import OllamaLLM
from app.agent.nlu import TurnUnderstanding, understand_turn
from app.agent.router import route
from app.agent.summarizer import summarize_call
from app.core.config import Settings
from app.core.config import settings as global_settings
from app.core.consent import has_current_owner_consent
from app.core.db import SessionLocal
from app.core.safe_http import SafeHttpClient
from app.core.security import hash_vip_number
from app.interfaces import LLM, STT, TTS, FakeLLM, FakeSTT
from app.models import AgentConfig as AgentConfigRecord
from app.schemas import (
    AgentConfig,
    Caller,
    CallResult,
    CallSlots,
    Handoff,
    TranscriptSegment,
    TranscriptWord,
)
from app.voice.phrases_cache import PhrasesCache, opening_phrases
from app.voice.protocol import (
    ClientEnd,
    ClientStart,
    ClientTestAudio,
    ServerEnd,
    ServerError,
    ServerHandoff,
    ServerPlayback,
    ServerState,
    ServerTranscript,
    parse_client_message,
)
from app.voice.stt import FasterWhisperSTT
from app.voice.tts import LocalTTS
from app.voice.vad import SileroVAD, VADSegmenter

logger = logging.getLogger(__name__)

# Global lock for single-call concurrency in demo mode
_ACTIVE_CALLS_LOCK = asyncio.Lock()
_ACTIVE_CALLS: set[str] = set()


def mask_phone_number(raw_phone: str) -> str:
    """Mask phone number safely ensuring <= 6 digits for privacy filters."""
    digits = "".join(c for c in raw_phone if c.isdigit())
    if len(digits) >= 10:
        return f"+{digits[:3]} *** ***-**-{digits[-2:]}"
    return "+*** ***-**-**"


class CallSession:
    """Manages one incoming audio call over WebSocket."""

    def __init__(
        self,
        websocket: WebSocket,
        *,
        settings: Settings | None = None,
        stt: STT | None = None,
        tts: TTS | None = None,
        vad: SileroVAD | Any | None = None,
        llm: LLM | None = None,
        phrases_cache: PhrasesCache | None = None,
        session_factory: Callable[[], Session] | None = None,
        ingest_url: str | None = None,
    ) -> None:
        self.websocket = websocket
        self.settings = settings or getattr(websocket.app.state, "settings", global_settings)
        self.session_factory = session_factory or SessionLocal
        self.ingest_url = ingest_url or f"{self.settings.public_base_url}/api/calls/ingest"

        # Lazy / injected adapters
        self._stt = stt
        self._tts = tts
        self._vad = vad
        self._llm = llm
        self._phrases_cache = phrases_cache

        self.call_id = str(uuid4())
        self.started_at = datetime.now(UTC)
        self.dialog = DialogSession(max_turns=8, max_reasks=2)
        self.transcript_segments: list[TranscriptSegment] = []
        self.is_vip = False
        self.caller_masked = "+*** ***-**-**"
        self.caller_hash: str | None = None
        self.handoff_performed = False
        self.handoff_reason: str | None = None
        self.last_turn: TurnUnderstanding | None = None
        self.config: AgentConfig | None = None

    def _init_adapters(self) -> None:
        """Initialize voice adapters with local models or fallbacks."""
        if self._tts is None:
            self._tts = LocalTTS()

        if self._phrases_cache is None:
            self._phrases_cache = PhrasesCache(self._tts)

        if self._stt is None:
            whisper_path = Path("models/whisper-small")
            if whisper_path.exists():
                try:
                    self._stt = FasterWhisperSTT(model_path=whisper_path)
                except (ImportError, OSError, RuntimeError, ValueError):
                    logger.warning("Failed to initialize FasterWhisperSTT")
                    self._stt = FakeSTT()
            else:
                self._stt = FakeSTT()

        if self._vad is None:
            try:
                silero_vad = SileroVAD()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to initialize SileroVAD; using energy fallback")
                self._vad = lambda pcm, sr: 0.8 if any(pcm) else 0.0
            else:
                # SileroVAD loads its optional model lazily, so constructor-only
                # handling leaves missing voice dependencies to crash the call
                # when the first microphone frame arrives. Switch to the local
                # energy fallback if model loading/inference fails at that point.
                silero_failed = False

                def resilient_vad(pcm: bytes, sample_rate: int) -> float:
                    nonlocal silero_failed
                    if not silero_failed:
                        try:
                            return silero_vad.speech_probability(pcm, sample_rate)
                        except Exception:  # noqa: BLE001
                            logger.exception("SileroVAD failed; using energy fallback")
                            silero_failed = True
                    return 0.8 if any(pcm) else 0.0

                self._vad = resilient_vad

        if self._llm is None:
            if self.settings.nlu_mode == "llm" and self.settings.llm_base_url:
                self._llm = OllamaLLM(
                    base_url=self.settings.llm_base_url,
                    model=self.settings.llm_model,
                )
            else:
                self._llm = FakeLLM()

    async def run(self) -> None:
        """Execute the full call lifecycle."""
        # 1. Concurrency check
        async with _ACTIVE_CALLS_LOCK:
            if len(_ACTIVE_CALLS) >= self.settings.max_concurrent_calls:
                await self.websocket.send_text(
                    ServerError(code="busy", message="Линия занята другим звонком").model_dump_json()
                )
                await self.websocket.close(code=1013, reason="Busy")
                return
            _ACTIVE_CALLS.add(self.call_id)

        try:
            await self._run_call_flow()
        except WebSocketDisconnect:
            logger.info("Call %s disconnected by client", self.call_id)
        except Exception:  # noqa: BLE001
            logger.exception("Error in call session %s", self.call_id)
            try:
                await self.websocket.send_text(
                    ServerError(code="internal", message="Внутренняя ошибка сервиса").model_dump_json()
                )
            except (WebSocketDisconnect, RuntimeError):
                logger.debug("Could not send the internal-error frame")
        finally:
            async with _ACTIVE_CALLS_LOCK:
                _ACTIVE_CALLS.discard(self.call_id)

    async def _run_call_flow(self) -> None:
        # 2. Check consent and config
        with self.session_factory() as db:
            if not has_current_owner_consent(db):
                await self.websocket.send_text(
                    ServerError(
                        code="consent_missing",
                        message="Согласие владельца не получено. Примите согласие в мастере настройки.",
                    ).model_dump_json()
                )
                await self.websocket.close(code=1008, reason="Consent missing")
                return

            latest_config = db.scalar(
                select(AgentConfigRecord).order_by(AgentConfigRecord.version.desc()).limit(1)
            )
            if latest_config is None:
                await self.websocket.send_text(
                    ServerError(
                        code="internal",
                        message="Конфигурация ассистента не найдена.",
                    ).model_dump_json()
                )
                await self.websocket.close(code=1013, reason="Config missing")
                return

            self.config = AgentConfig.model_validate(latest_config.config_json)

        # 3. Wait for client start frame
        try:
            first_msg = await asyncio.wait_for(self.websocket.receive_text(), timeout=10.0)
            parsed_start = parse_client_message(first_msg)
            if not isinstance(parsed_start, ClientStart):
                await self.websocket.close(code=1003, reason="Expected start message")
                return
            caller_raw = parsed_start.caller_number
        except (TimeoutError, WebSocketDisconnect):
            await self.websocket.close(code=1002, reason="Start handshake timeout")
            return

        # 4. VIP matching and caller privacy
        self._init_adapters()
        self._phrases_cache.preload(self.config)

        self.caller_masked = mask_phone_number(caller_raw)
        enc_key = self.settings.data_encryption_key
        if enc_key and enc_key.get_secret_value():
            self.caller_hash = hash_vip_number(caller_raw, enc_key.get_secret_value())
            if self.caller_hash in (self.config.vip_numbers or []):
                self.is_vip = True

        # 5. Mandatory Opening: Greeting + Disclosure (FR-02)
        await self.websocket.send_text(ServerState(state="GREET").model_dump_json())
        greeting, disclosure = opening_phrases(self.config)
        greeting_text = f"{greeting} {disclosure}"
        await self.websocket.send_text(
            ServerTranscript(who="agent", text=greeting_text).model_dump_json()
        )
        self.transcript_segments.append(
            TranscriptSegment(who="agent", text=greeting_text, start_s=0.0)
        )

        await self._send_playback_audio(
            self._phrases_cache.get("greeting", greeting)
            + self._phrases_cache.get("disclosure", disclosure)
        )

        # Transition dialog to ASK_NAME_COMPANY
        self.dialog.state = DialogState.ASK_NAME_COMPANY
        await self.websocket.send_text(ServerState(state="ASK_NAME_COMPANY").model_dump_json())

        # 6. Audio loop with VAD segmenter
        segmenter = VADSegmenter(self._vad, silence_duration_ms=700)
        end_reason = "completed"

        while True:
            try:
                # 30-second idle timeout without speech (FR-03 / contracts)
                message = await asyncio.wait_for(self.websocket.receive(), timeout=30.0)
            except TimeoutError:
                end_reason = "timeout"
                close_phrase = "К сожалению, вас не слышно. Я завершаю звонок. Всего доброго!"
                await self._say_agent_phrase(close_phrase)
                break

            if message.get("type") == "websocket.disconnect":
                end_reason = "completed"
                break

            # Handle binary audio frame from caller
            if pcm_chunk := message.get("bytes"):
                utterances = segmenter.feed(pcm_chunk)
                terminated = False
                for utterance in utterances:
                    terminated = await self._process_utterance(utterance)
                    if terminated:
                        end_reason = "handoff" if self.handoff_performed else "completed"
                        break
                if terminated:
                    break

            # Handle text control frame
            elif text_frame := message.get("text"):
                parsed = parse_client_message(text_frame)
                if isinstance(parsed, ClientEnd):
                    end_reason = "completed"
                    break
                if isinstance(parsed, ClientTestAudio):
                    terminated = await self._handle_test_audio(parsed.fixture)
                    if terminated:
                        end_reason = "handoff" if self.handoff_performed else "completed"
                        break

        # 7. Wrap up call and save CallResult
        await self._finalize_call(end_reason)

    async def _process_utterance(self, utterance_pcm: bytes) -> bool:
        """Process one caller utterance ended by VAD silence."""
        transcript_obj = self._stt.transcribe(utterance_pcm, 16000)
        text = transcript_obj.text.strip()
        if not text:
            return False

        # NLU Turn Understanding
        turn = await understand_turn(text, llm=self._llm, mode=self.settings.nlu_mode)
        self.last_turn = turn
        if turn.no_record:
            self.dialog.update_slots(turn)
            return await self._finish_no_record_call()

        # Caller transcript frame
        await self.websocket.send_text(ServerTranscript(who="caller", text=text).model_dump_json())
        words = [TranscriptWord(w=item.w, p=item.p) for item in transcript_obj.words]
        self.transcript_segments.append(
            TranscriptSegment(who="caller", text=text, words=words)
        )

        # Router rule evaluation
        routed_action = route(
            rules=self.config.routing or [],
            turn=turn,
            is_vip=self.is_vip,
            outside_hours=False,
        )

        faq_answer = None
        if routed_action == "answer_faq" and turn.faq_id and self.config.faq:
            for item in self.config.faq:
                if item.id == turn.faq_id:
                    faq_answer = item.answer
                    break

        # Dialogue state machine step
        turn_result = self.dialog.process_turn(
            turn,
            routed_action=routed_action,
            faq_answer=faq_answer,
        )

        await self.websocket.send_text(
            ServerState(state=turn_result.next_state.value).model_dump_json()
        )

        # Handoff notification
        if turn_result.action == "handoff" or turn_result.next_state == DialogState.HANDOFF:
            self.handoff_performed = True
            self.handoff_reason = (
                "wants_human" if turn.wants_human else "vip" if self.is_vip else "urgent_rule"
            )
            await self.websocket.send_text(
                ServerHandoff(
                    number=self.config.handoff_number,
                    reason=self.handoff_reason,
                ).model_dump_json()
            )

        # Agent response speech
        await self._say_agent_phrase(turn_result.agent_phrase)
        return turn_result.is_terminal

    async def _handle_test_audio(self, fixture_name: str) -> bool:
        """Handle demo fallback test audio."""
        if fixture_name == "s1_urgent_client":
            text = (
                "Здравствуйте! Меня зовут Алексей, компания Вектор. "
                "Нам нужно согласовать договор до пятницы, срочно! Перезвоните мне, пожалуйста."
            )
        else:
            text = "Здравствуйте! Хочу уточнить ваш график работы и адрес офиса."

        # Simulate caller speech from fixture text
        turn = await understand_turn(text, llm=self._llm, mode=self.settings.nlu_mode)
        self.last_turn = turn
        if turn.no_record:
            self.dialog.update_slots(turn)
            return await self._finish_no_record_call()

        await self.websocket.send_text(ServerTranscript(who="caller", text=text).model_dump_json())
        self.transcript_segments.append(TranscriptSegment(who="caller", text=text))

        routed_action = route(
            rules=self.config.routing or [],
            turn=turn,
            is_vip=self.is_vip,
            outside_hours=False,
        )

        turn_result = self.dialog.process_turn(turn, routed_action=routed_action)
        await self.websocket.send_text(
            ServerState(state=turn_result.next_state.value).model_dump_json()
        )

        if turn_result.action == "handoff":
            self.handoff_performed = True
            self.handoff_reason = "wants_human" if turn.wants_human else "urgent_rule"
            await self.websocket.send_text(
                ServerHandoff(
                    number=self.config.handoff_number,
                    reason=self.handoff_reason,
                ).model_dump_json()
            )

        await self._say_agent_phrase(turn_result.agent_phrase)
        return turn_result.is_terminal

    async def _finish_no_record_call(self) -> bool:
        """End a call without retaining its transcript or caller-provided details."""
        callback_number = self.dialog.slots.callback_number
        self.dialog.slots = CallSlots(callback_number=callback_number)
        self.transcript_segments.clear()
        await self.websocket.send_text(ServerState(state=DialogState.CLOSE.value).model_dump_json())
        await self._say_agent_phrase(
            "Понимаю. Содержание разговора не будет сохранено. Всего доброго."
        )
        return True

    async def _say_agent_phrase(self, phrase: str) -> None:
        """Send agent transcript, playback start, audio frames, and playback stop."""
        await self.websocket.send_text(ServerTranscript(who="agent", text=phrase).model_dump_json())
        if not self.dialog.no_record:
            self.transcript_segments.append(TranscriptSegment(who="agent", text=phrase))
        audio = self._tts.synth(phrase)
        await self._send_playback_audio(audio)

    async def _send_playback_audio(self, pcm_bytes: bytes) -> None:
        """Stream binary PCM frames to the client surrounded by playback start/stop."""
        await self.websocket.send_text(ServerPlayback(action="start").model_dump_json())
        if pcm_bytes:
            chunk_size = 4096
            for offset in range(0, len(pcm_bytes), chunk_size):
                chunk = pcm_bytes[offset : offset + chunk_size]
                await self.websocket.send_bytes(chunk)
                await asyncio.sleep(0.01)
        await self.websocket.send_text(ServerPlayback(action="stop").model_dump_json())

    async def _finalize_call(self, reason: str) -> None:
        """Build CallResult, send ServerEnd, and ingest to platform."""
        ended_at = datetime.now(UTC)
        duration_s = max(0.0, round((ended_at - self.started_at).total_seconds(), 2))

        if self.dialog.no_record:
            self.transcript_segments.clear()
            slots = CallSlots(callback_number=self.dialog.slots.callback_number)
            summary_ru = ""
        else:
            slots = self.dialog.slots
            summary_ru = await summarize_call(
                self.transcript_segments,
                slots,
                llm=self._llm,
            )

            # Fallback slots callback number to caller number if left blank
            if not slots.callback_number and self.caller_masked != "+*** ***-**-**":
                slots.callback_number = self.caller_masked

        call_result = CallResult(
            call_id=self.call_id,
            started_at=self.started_at,
            ended_at=ended_at,
            duration_s=duration_s,
            caller=Caller(
                masked=self.caller_masked,
                hash=self.caller_hash,
                is_vip=self.is_vip,
            ),
            transcript=self.transcript_segments,
            intent=self.last_turn.intent if self.last_turn else "unclear",
            urgency=self.last_turn.urgency if self.last_turn else "normal",
            slots=slots,
            summary_ru=summary_ru,
            action=self.dialog.chosen_action or "take_message",
            handoff=Handoff(performed=True, reason=self.handoff_reason)
            if self.handoff_performed
            else None,
            no_record=self.dialog.no_record,
        )

        # Notify client of call end
        try:
            await self.websocket.send_text(
                ServerEnd(call_id=self.call_id, reason=reason).model_dump_json()
            )
            await self.websocket.close(code=1000, reason="Call ended")
        except (WebSocketDisconnect, RuntimeError):
            logger.debug("Client disconnected before call completion")

        # Ingest CallResult to Dev B's loopback endpoint
        await self._ingest_call_result(call_result)

    async def _ingest_call_result(self, result: CallResult) -> None:
        """Send CallResult to the local ingestion endpoint via SafeHttpClient."""
        client = SafeHttpClient()
        try:
            payload = result.model_dump(mode="json")
            response = await client.request(
                "POST",
                self.ingest_url,
                json=payload,
                timeout=5.0,
            )
            if response.status_code in (200, 201):
                logger.info("Successfully ingested CallResult %s", result.call_id)
            else:
                logger.warning("CallResult ingest returned status %s", response.status_code)
        except (HTTPError, ValueError):
            logger.warning("Failed to POST CallResult")
        finally:
            await client.aclose()
