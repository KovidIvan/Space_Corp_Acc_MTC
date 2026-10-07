"""Pydantic v2 models mirroring the frozen JSON contracts."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["client", "partner", "vendor_sales", "spam", "job_candidate", "other", "unclear"]
Urgency = Literal["low", "normal", "high"]
Action = Literal["answer_faq", "take_message", "offer_chat", "handoff", "decline"]


class ContractModel(BaseModel):
    """Base schema model allowing extra fields as JSON Schema does by default."""

    model_config = ConfigDict(extra="allow")


class AgentOwner(ContractModel):
    name: str
    company: str
    role: str | None = None


class FAQItem(ContractModel):
    id: str
    question: str
    answer: str


class Example(ContractModel):
    utterance: str
    intent: Intent
    urgency: Urgency


class RuleWhen(ContractModel):
    intent: list[Intent] | None = None
    urgency: list[Urgency] | None = None
    is_vip: bool | None = None
    outside_hours: bool | None = None
    wants_human: bool | None = None
    wants_chat: bool | None = None


class RoutingRule(ContractModel):
    id: str
    priority: int
    action: Action
    when: RuleWhen | None = None


class WorkingHours(ContractModel):
    tz: str | None = None
    days: list[Annotated[int, Field(ge=1, le=7)]] | None = None
    start: str | None = None
    end: str | None = None


class AgentConfig(ContractModel):
    version: int = Field(ge=1)
    owner: AgentOwner
    greeting: str
    disclosure: str
    closing: str
    routing: list[RoutingRule]
    handoff_number: str
    template: str | None = None
    faq: list[FAQItem] | None = None
    examples: list[Example] | None = None
    vip_numbers: list[str] | None = None
    working_hours: WorkingHours | None = None
    retention_days: int = Field(default=30, ge=0)
    store_audio: bool = False
    notice_detail: Literal["minimal", "names"] = "minimal"


class Caller(ContractModel):
    masked: str
    hash: str | None = None
    is_vip: bool | None = None


class TranscriptWord(ContractModel):
    w: str
    p: float = Field(ge=0, le=1)


class TranscriptSegment(ContractModel):
    who: Literal["caller", "agent"]
    text: str
    start_s: float | None = None
    words: list[TranscriptWord] | None = None


class CallSlots(ContractModel):
    name: str | None = None
    company: str | None = None
    reason: str | None = None
    callback_number: str | None = None
    deadline: str | None = None


class Handoff(ContractModel):
    performed: bool | None = None
    reason: str | None = None


class CallResult(ContractModel):
    call_id: str
    started_at: datetime
    ended_at: datetime
    caller: Caller
    transcript: list[TranscriptSegment]
    intent: Intent
    urgency: Urgency
    slots: CallSlots
    summary_ru: str
    action: Action
    duration_s: float | None = None
    handoff: Handoff | None = None
    no_record: bool = False
    stt_avg_conf: float | None = None
    latency_ms_p50: float | None = None


class CallEdit(ContractModel):
    """Editable call fields accepted from an authenticated dashboard owner."""

    model_config = ConfigDict(extra="forbid")

    transcript: list[TranscriptSegment] | None = None
    summary: str | None = None
    intent: Intent | None = None
    urgency: Urgency | None = None
    action: Action | None = None
