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
    role: str = Field(default=None)


class FAQItem(ContractModel):
    id: str
    question: str
    answer: str


class Example(ContractModel):
    utterance: str
    intent: Intent
    urgency: Urgency


class RuleWhen(ContractModel):
    intent: list[Intent] = Field(default=None)
    urgency: list[Urgency] = Field(default=None)
    is_vip: bool = Field(default=None)
    outside_hours: bool = Field(default=None)
    wants_human: bool = Field(default=None)
    wants_chat: bool = Field(default=None)


class RoutingRule(ContractModel):
    id: str
    priority: int
    action: Action
    when: RuleWhen = Field(default=None)


class WorkingHours(ContractModel):
    tz: str = Field(default=None)
    days: list[Annotated[int, Field(ge=1, le=7)]] = Field(default=None)
    start: str = Field(default=None)
    end: str = Field(default=None)


class AgentConfig(ContractModel):
    version: int = Field(ge=1)
    owner: AgentOwner
    greeting: str
    disclosure: str
    closing: str
    routing: list[RoutingRule]
    handoff_number: str
    template: str = Field(default=None)
    faq: list[FAQItem] = Field(default=None)
    examples: list[Example] = Field(default=None)
    vip_numbers: list[str] = Field(default=None)
    working_hours: WorkingHours = Field(default=None)
    retention_days: int = Field(default=30, ge=0)
    store_audio: bool = False
    notice_detail: Literal["minimal", "names"] = "minimal"


class Caller(ContractModel):
    masked: str
    hash: str = Field(default=None)
    is_vip: bool = Field(default=None)


class TranscriptWord(ContractModel):
    w: str
    p: float = Field(ge=0, le=1)


class TranscriptSegment(ContractModel):
    who: Literal["caller", "agent"]
    text: str
    start_s: float = Field(default=None)
    words: list[TranscriptWord] = Field(default=None)


class CallSlots(ContractModel):
    name: str | None = None
    company: str | None = None
    reason: str | None = None
    callback_number: str | None = None
    deadline: str | None = None


class Handoff(ContractModel):
    performed: bool = Field(default=None)
    reason: str = Field(default=None)


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
    duration_s: float = Field(default=None)
    handoff: Handoff = Field(default=None)
    no_record: bool = False
    stt_avg_conf: float = Field(default=None)
    latency_ms_p50: float = Field(default=None)
