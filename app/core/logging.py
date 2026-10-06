"""PII masking utilities for log records."""

import logging
import re

EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d().\s-]{5,}\d(?!\w)")
LONG_DIGIT_PATTERN = re.compile(r"\d{6,}")


def mask_pii(value: str) -> str:
    """Replace email addresses, phone numbers, and long digit runs."""
    masked = EMAIL_PATTERN.sub("[EMAIL]", value)
    masked = PHONE_PATTERN.sub(
        lambda match: (
            "[PHONE]"
            if sum(char.isdigit() for char in match.group()) >= 7
            and (match.group().lstrip().startswith("+") or any(char in match.group() for char in "(). -"))
            else match.group()
        ),
        masked,
    )
    return LONG_DIGIT_PATTERN.sub("[DIGITS]", masked)


class PiiMaskFilter(logging.Filter):
    """Mask PII in the rendered log message before it reaches a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize a log record in place and allow it to be emitted."""
        record.msg = mask_pii(record.getMessage())
        record.args = ()
        return True
