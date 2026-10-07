"""Routing engine: apply ordered rules to an NLU result and pick an action.

Architecture (§4 Call flow, FR-05, FR-06):
    TurnUnderstanding → Router → Action

Rules are evaluated in priority order (lower number first).  The first rule
whose ``when`` conditions all match wins.  A missing ``when`` field means
"always matches" (catch-all).

Emergency handoff (FR-06): ``wants_human=True``, a VIP number, or an urgent
routing rule triggers ``handoff`` immediately.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.agent.nlu import TurnUnderstanding
from app.schemas import Action, RoutingRule

logger = logging.getLogger(__name__)


def _matches_rule(
    rule: RoutingRule,
    turn: TurnUnderstanding,
    *,
    is_vip: bool = False,
    outside_hours: bool = False,
) -> bool:
    """Check whether all non-null conditions in *rule.when* match the turn."""
    when = rule.when
    if when is None:
        return True  # catch-all

    if when.intent is not None and turn.intent not in when.intent:
        return False
    if when.urgency is not None and turn.urgency not in when.urgency:
        return False
    if when.is_vip is not None and when.is_vip != is_vip:
        return False
    if when.outside_hours is not None and when.outside_hours != outside_hours:
        return False
    if when.wants_human is not None and when.wants_human != turn.wants_human:
        return False
    return not (when.wants_chat is not None and when.wants_chat != turn.wants_chat)


def route(
    turn: TurnUnderstanding,
    rules: Sequence[RoutingRule],
    *,
    is_vip: bool = False,
    outside_hours: bool = False,
) -> Action:
    """Evaluate routing rules against a turn understanding and return the winning action.

    Args:
        turn: Current turn NLU result.
        rules: Ordered list of ``RoutingRule`` objects (sorted by priority ascending).
        is_vip: Whether the caller number matched the VIP list.
        outside_hours: Whether the current time is outside working hours.

    Returns:
        The action from the first matching rule, or ``"take_message"`` if no
        rule matches.
    """
    # FR-06 emergency handoff: explicit request overrides all rules
    if turn.wants_human:
        logger.info("Caller wants human → immediate handoff")
        return "handoff"

    # VIP callers get handoff by default unless a specific VIP rule exists
    if is_vip:
        # Check if there's a VIP-specific rule first
        for rule in sorted(rules, key=lambda r: r.priority):
            if rule.when is not None and rule.when.is_vip is True and _matches_rule(rule, turn, is_vip=is_vip, outside_hours=outside_hours):
                logger.info("VIP matched rule %s → %s", rule.id, rule.action)
                return rule.action
        logger.info("VIP caller, no specific rule → handoff")
        return "handoff"

    # Evaluate rules in priority order
    sorted_rules = sorted(rules, key=lambda r: r.priority)
    for rule in sorted_rules:
        if _matches_rule(rule, turn, is_vip=is_vip, outside_hours=outside_hours):
            logger.info("Matched rule %s → %s", rule.id, rule.action)
            return rule.action

    # Default: take a message if nothing else matches
    logger.info("No rule matched → take_message")
    return "take_message"
