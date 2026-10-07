"""Dialogue state machine managing turn progression, slot filling, and fallback rules.

Architecture (§4 Call flow, FR-03):
    GREET -> ASK_NAME_COMPANY -> ASK_REASON -> ROUTE -> (FAQ_ANSWER | TAKE_MESSAGE | OFFER_CHAT | HANDOFF | DECLINE) -> CONFIRM -> CLOSE
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.agent.nlu import TurnUnderstanding
from app.schemas import Action, CallSlots


class DialogState(str, Enum):
    GREET = "GREET"
    ASK_NAME_COMPANY = "ASK_NAME_COMPANY"
    ASK_REASON = "ASK_REASON"
    ROUTE = "ROUTE"
    FAQ_ANSWER = "FAQ_ANSWER"
    TAKE_MESSAGE = "TAKE_MESSAGE"
    OFFER_CHAT = "OFFER_CHAT"
    HANDOFF = "HANDOFF"
    DECLINE = "DECLINE"
    CONFIRM = "CONFIRM"
    CLOSE = "CLOSE"


class DialogTurnResult(BaseModel):
    """Output of processing one caller turn through the dialogue manager."""

    next_state: DialogState
    agent_phrase: str
    action: Action | None = None
    slots: CallSlots = Field(default_factory=CallSlots)
    is_terminal: bool = False
    reask_count: int = 0


class DialogSession:
    """Manages state, slots, turn limits and re-asks for a single call session."""

    def __init__(self, max_turns: int = 8, max_reasks: int = 2) -> None:
        self.state = DialogState.GREET
        self.turns_count = 0
        self.reask_count = 0
        self.max_turns = max_turns
        self.max_reasks = max_reasks
        self.slots = CallSlots()
        self.no_record = False
        self.chosen_action: Action | None = None

    def update_slots(self, turn: TurnUnderstanding) -> None:
        """Merge newly extracted slots into accumulated call slots."""
        if turn.slots.name and not self.slots.name:
            self.slots.name = turn.slots.name
        if turn.slots.company and not self.slots.company:
            self.slots.company = turn.slots.company
        if turn.slots.reason and not self.slots.reason:
            self.slots.reason = turn.slots.reason
        if turn.slots.callback_number and not self.slots.callback_number:
            self.slots.callback_number = turn.slots.callback_number
        if turn.slots.deadline and not self.slots.deadline:
            self.slots.deadline = turn.slots.deadline
        if turn.no_record:
            self.no_record = True

    def process_turn(
        self,
        turn: TurnUnderstanding,
        routed_action: Action | None = None,
        faq_answer: str | None = None,
    ) -> DialogTurnResult:
        """Advance dialogue state machine based on caller NLU understanding."""
        self.turns_count += 1
        self.update_slots(turn)

        # 1. Turn limit check (FR-03: Max 8 turns)
        if self.turns_count >= self.max_turns:
            self.state = DialogState.CLOSE
            return DialogTurnResult(
                next_state=DialogState.CLOSE,
                agent_phrase="Время вызова истекло. Я передам информацию руководителю. До свидания!",
                action=self.chosen_action or "take_message",
                slots=self.slots,
                is_terminal=True,
            )

        # 2. Immediate handoff check (FR-06)
        if turn.wants_human:
            self.state = DialogState.HANDOFF
            self.chosen_action = "handoff"
            return DialogTurnResult(
                next_state=DialogState.HANDOFF,
                agent_phrase="Соединяю вас с менеджером. Пожалуйста, подождите.",
                action="handoff",
                slots=self.slots,
                is_terminal=True,
            )

        # 3. Handle silence / unclear speech re-asks (FR-03)
        if (
            turn.intent == "unclear"
            and not any([self.slots.name, self.slots.reason])
            and self.reask_count < self.max_reasks
        ):
            self.reask_count += 1
            return DialogTurnResult(
                next_state=self.state,
                agent_phrase="Извините, плохо вас слышно. Повторите, пожалуйста, как к вам обращаться и цель звонка?",
                action=self.chosen_action,
                slots=self.slots,
                reask_count=self.reask_count,
            )

        # 4. State transitions
        if self.state in (DialogState.GREET, DialogState.ASK_NAME_COMPANY):
            if not self.slots.name:
                self.state = DialogState.ASK_NAME_COMPANY
                return DialogTurnResult(
                    next_state=DialogState.ASK_NAME_COMPANY,
                    agent_phrase="Представьтесь, пожалуйста, как к вам обращаться?",
                    slots=self.slots,
                )
            self.state = DialogState.ASK_REASON

        if self.state == DialogState.ASK_REASON:
            if not self.slots.reason:
                return DialogTurnResult(
                    next_state=DialogState.ASK_REASON,
                    agent_phrase="Уточните, пожалуйста, по какому вы вопросу?",
                    slots=self.slots,
                )
            self.state = DialogState.ROUTE

        if self.state == DialogState.ROUTE:
            action = routed_action or "take_message"
            self.chosen_action = action

            if action == "answer_faq":
                self.state = DialogState.FAQ_ANSWER
                phrase = faq_answer or "Благодарю за вопрос. Наша компания работает по будням с 9 до 18."
            elif action == "decline":
                self.state = DialogState.DECLINE
                phrase = "Спасибо за предложение, но в данный момент мы не заинтересованы. Всего доброго!"
            elif action == "offer_chat":
                self.state = DialogState.OFFER_CHAT
                phrase = "Внешний чат недоступен в локальном режиме. Я зафиксирую ваше обращение."
            elif action == "handoff":
                self.state = DialogState.HANDOFF
                phrase = "Переключаю вас на руководителя. Оставайтесь на линии."
            else:
                self.state = DialogState.TAKE_MESSAGE
                phrase = "Я записал ваше сообщение и передам его Ивану. С вами свяжутся в ближайшее время."

            is_terminal = action in ("decline", "handoff")
            if is_terminal:
                self.state = DialogState.CLOSE

            return DialogTurnResult(
                next_state=self.state,
                agent_phrase=phrase,
                action=action,
                slots=self.slots,
                is_terminal=is_terminal,
            )

        # Default fallback transition to polite closing
        self.state = DialogState.CLOSE
        return DialogTurnResult(
            next_state=DialogState.CLOSE,
            agent_phrase="Спасибо! Информация принята. Всего вам доброго!",
            action=self.chosen_action or "take_message",
            slots=self.slots,
            is_terminal=True,
        )
