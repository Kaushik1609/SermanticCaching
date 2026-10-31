"""CacheIQ Time-Sensitive Query Detector.

Source of truth: PRD §4.3.
Case-insensitive match on whole words/phrases.
Exported as one constant list so Builder 2's dataset tests can import it directly.
"""

import re
from typing import List

# Frozen list from PRD §4.3
TIME_SENSITIVE_WORDS: List[str] = [
    "latest",
    "newest",
    "current",
    "currently",
    "today",
    "tonight",
    "tomorrow",
    "yesterday",
    "now",
    "right now",
    "this week",
    "this month",
    "this year",
    "recent",
    "recently",
    "price",
    "weather",
    "score",
    "news",
    "as of",
]

# Compile case-insensitive regex pattern matching whole words or multi-word phrases
_pattern = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in sorted(TIME_SENSITIVE_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def is_time_sensitive(text: str) -> bool:
    """Return True if the text contains any time-sensitive keyword or phrase."""
    if not text:
        return False
    return bool(_pattern.search(text))

