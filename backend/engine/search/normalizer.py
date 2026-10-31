"""Query Normalization & Exact Key Hashing.

Rules from PRD §3:
- Normalization (normalize(q)): Unicode NFKC, trim, collapse whitespace.
  Casing is KEPT for the embedding.
  Lowercasing is used ONLY for the exact-match key.
- exact_key = sha256(lower(normalize(q)) + "|" + context_key + "|" + config_hash)
- config_hash = sha256(provider | model | temperature | system_prompt)
"""

import hashlib
import unicodedata
import re


def normalize(query: str) -> str:
    """Normalize query text: Unicode NFKC, collapse whitespace, strip leading/trailing spaces.

    Notice: Letter casing is preserved here because embedding models benefit from casing.
    """
    if not query:
        return ""
    # Unicode NFKC
    text = unicodedata.normalize("NFKC", query)
    # Collapse multiple whitespace characters into single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compute_config_hash(
    provider: str = "mock",
    model: str = "default",
    temperature: float = 0.0,
    system_prompt: str = "",
) -> str:
    """Hash LLM generation configuration to ensure answers are only reused under identical configs."""
    raw = f"{provider.lower()}|{model.lower()}|{temperature}|{system_prompt.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compute_exact_key(
    query: str,
    context_key: str = "default",
    config_hash: str = "default_config",
) -> str:
    """Compute 64-char SHA256 exact match key.

    Lowercases normalized query specifically for exact key matching.
    """
    norm_lower = normalize(query).lower()
    raw = f"{norm_lower}|{context_key}|{config_hash}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

