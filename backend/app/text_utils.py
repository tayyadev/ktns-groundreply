"""Deterministic text splitting and evidence/quality checks; no LLM dependencies."""
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Evidence:
    id: str
    document_id: str
    title: str
    content: str
    similarity: float


def chunk_text(text: str, chunk_size: int = 1100, overlap: int = 140) -> list[str]:
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must be shorter than chunk_size")
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n")).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = max(normalized.rfind("\n", start + chunk_size // 2, end), normalized.rfind(". ", start + chunk_size // 2, end))
            if boundary > start + chunk_size // 2:
                end = boundary + 1
        chunks.append(normalized[start:end].strip())
        if end == len(normalized):
            break
        start = max(start + 1, end - overlap)
    return [part for part in chunks if part]


def vetted_citations(requested: list[str], evidence: list[Evidence]) -> list[dict[str, Any]]:
    allowed = {s.id: s for s in evidence}
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []
    for candidate in requested:
        if candidate in allowed and candidate not in seen:
            s = allowed[candidate]
            citations.append({
                "ref": s.id, "document_id": s.document_id,
                "title": s.title, "excerpt": s.content[:450],
                "similarity": round(s.similarity, 3),
            })
            seen.add(candidate)
    return citations


def should_escalate(no_sources: bool, citations: list, reviewer_supported: bool, risky: bool) -> bool:
    return no_sources or not citations or not reviewer_supported or risky


def safety_flags(question: str, draft: str) -> list[str]:
    """Conservative escalation checks: not a substitute for provider DLP/PII scanning."""
    value = f"{question}\n{draft}".lower()
    flags = []
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b", value):
        flags.append("Potential US Social Security number in request or draft")
    if re.search(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", value):
        flags.append("Potential payment-card number in request or draft")
    if any(term in value for term in ("wire transfer", "change bank", "routing number", "change password", "account credentials")):
        flags.append("Potential financial, authentication, or account-change request")
    return flags


def evaluation_passed(answer: str, citations: list, must_include: str | None, expect_abstain: bool, abstained: bool, review_ok: bool = True) -> bool:
    if expect_abstain:
        return abstained
    if abstained or not citations or not review_ok:
        return False
    return must_include is None or must_include.casefold() in answer.casefold()
