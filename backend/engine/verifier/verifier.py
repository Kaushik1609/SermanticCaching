"""CacheIQ Match Verifier.

CRITICAL ARCHITECTURAL RULE (AGENTS.md):
- engine/verifier must NOT import from engine/search or engine/store.
- Pure function decision logic.

Rules run in this EXACT order (PRD §4.2):
V1: candidate.expires_at is null or in the future -> MISS_EXPIRED
V2: candidate.config_hash == request_config_hash -> MISS_CONFIG_MISMATCH
V3: candidate.embedding_model == current_model -> MISS_CONFIG_MISMATCH
V4: is_time_sensitive(new_query) == False and is_time_sensitive(candidate.query_text) == False -> MISS_TIME_SENSITIVE
V5: set of digit sequences in new_query == set in candidate.query_text -> MISS_NUMERIC_MISMATCH
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Set
import re

from backend.engine.verifier.time_sensitive import is_time_sensitive


@dataclass
class Verdict:
    ok: bool
    reason_code: str
    explain: str


def _extract_number_tokens(text: str) -> Set[str]:
    """Extract all digit sequences from text.

    Catches integers, years (2023 vs 2024), versions (3.11 -> {'3', '11'}), counts (5 vs 10).
    """
    if not text:
        return set()
    return set(re.findall(r"\d+", text))


def verify(
    new_query: str,
    candidate: Dict[str, Any],
    request_config_hash: str,
    now: datetime,
    current_model: str,
) -> Verdict:
    """Evaluate candidate match against Match Verifier rules V1..V5.

    The first failing rule halts verification and returns the corresponding reason code.
    """
    # ── Rule V1: Expiry check ──────────────────────────────────────────
    expires_at = candidate.get("expires_at")
    if expires_at is not None:
        # Handle naive and aware datetimes consistently
        if expires_at.tzinfo is None and now.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        elif expires_at.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        if expires_at <= now:
            return Verdict(
                ok=False,
                reason_code="MISS_EXPIRED",
                explain=f"Cached entry expired at {expires_at.isoformat()}.",
            )

    # ── Rule V2: LLM Configuration Hash ────────────────────────────────
    cand_config = candidate.get("config_hash", "")
    if cand_config and cand_config != request_config_hash:
        return Verdict(
            ok=False,
            reason_code="MISS_CONFIG_MISMATCH",
            explain="Candidate was generated under a different LLM model/config.",
        )

    # ── Rule V3: Embedding Model Match ─────────────────────────────────
    cand_model = candidate.get("embedding_model", "")
    if cand_model and cand_model != current_model:
        return Verdict(
            ok=False,
            reason_code="MISS_CONFIG_MISMATCH",
            explain=f"Candidate was embedded with '{cand_model}', current model is '{current_model}'.",
        )

    # ── Rule V4: Time-sensitivity Check ────────────────────────────────
    if is_time_sensitive(new_query):
        return Verdict(
            ok=False,
            reason_code="MISS_TIME_SENSITIVE",
            explain="Query contains time-sensitive words ('latest', 'today', 'price', etc.); bypassing cache.",
        )
    if is_time_sensitive(candidate.get("query_text", "")):
        return Verdict(
            ok=False,
            reason_code="MISS_TIME_SENSITIVE",
            explain="Cached entry is from a time-sensitive query; cannot be safely reused.",
        )

    # ── Rule V5: Numeric & Year Match ──────────────────────────────────
    cand_query = candidate.get("query_text", "")
    nums_new = _extract_number_tokens(new_query)
    nums_cand = _extract_number_tokens(cand_query)

    if nums_new != nums_cand:
        diff_detail = f"query has {sorted(nums_new)}, cached query has {sorted(nums_cand)}"
        return Verdict(
            ok=False,
            reason_code="MISS_NUMERIC_MISMATCH",
            explain=f"Numbers differ between queries: {diff_detail}.",
        )

    # ── All checks passed ──────────────────────────────────────────────
    return Verdict(
        ok=True,
        reason_code="HIT_SEMANTIC",
        explain="All verification checks passed.",
    )

