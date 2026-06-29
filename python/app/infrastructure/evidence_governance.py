"""Evidence governance - traceability, validation, and no-evidence conclusion checks

Rules:
  - 最终报告中的每条关键结论都可追溯
  - 过期或版本不适用的Runbook不会成为有效依据
  - 没有证据的假设不得排在第一位
  - 证据不足时输出 INCONCLUSIVE
"""

from dataclasses import dataclass, field

from app.domain.incident import ConfidenceLevel, Evidence, Hypothesis
from app.infrastructure.runbook_store import Runbook


@dataclass
class TraceabilityReport:
    """Report on evidence traceability for a diagnosis"""
    total_claims: int = 0
    traceable_claims: int = 0
    untraceable_claims: list[str] = field(default_factory=list)
    invalid_references: list[str] = field(default_factory=list)
    is_fully_traceable: bool = True


def validate_evidence_traceability(
    hypotheses: list[Hypothesis],
    evidence_collection: list[Evidence],
) -> TraceabilityReport:
    """Validate that all hypothesis claims reference real evidence.

    Returns a traceability report showing which claims are backed by evidence.
    """
    evidence_ids = {e.evidence_id for e in evidence_collection}
    total_claims = 0
    traceable = 0
    untraceable = []
    invalid_refs = []

    for h in hypotheses:
        # Check supporting evidence
        for eid in h.supporting_evidence:
            total_claims += 1
            if eid in evidence_ids:
                traceable += 1
            else:
                invalid_refs.append(f"{h.cause_code}: supporting evidence {eid} not found")

        # Check contradicting evidence
        for eid in h.contradicting_evidence:
            total_claims += 1
            if eid in evidence_ids:
                traceable += 1
            else:
                invalid_refs.append(f"{h.cause_code}: contradicting evidence {eid} not found")

        # A hypothesis with no evidence at all
        if not h.supporting_evidence and not h.contradicting_evidence:
            untraceable.append(f"{h.cause_code}: no evidence provided")

    is_fully_traceable = len(invalid_refs) == 0 and (traceable == total_claims)

    return TraceabilityReport(
        total_claims=total_claims,
        traceable_claims=traceable,
        untraceable_claims=untraceable,
        invalid_references=invalid_refs,
        is_fully_traceable=is_fully_traceable,
    )


def filter_hypotheses_without_evidence(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Remove hypotheses that have no supporting evidence at all.

    Rules:
    - 没有证据的假设不得排在第一位
    - 证据不足时不强行给出结论
    """
    with_evidence = [h for h in hypotheses if h.supporting_evidence]
    without_evidence = [h for h in hypotheses if not h.supporting_evidence]

    # Re-rank: hypotheses with evidence come first
    ranked = []
    rank = 1
    for h in with_evidence:
        h.rank = rank
        ranked.append(h)
        rank += 1

    # Add unverified hypotheses after, but demote confidence
    for h in without_evidence:
        h.confidence = ConfidenceLevel.LOW
        h.rank = rank
        ranked.append(h)
        rank += 1

    return ranked


def filter_expired_runbook_evidence(
    runbook_references: list[str],
    valid_runbook_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Filter out references to expired/deprecated runbooks.

    Returns (valid_refs, expired_refs).
    """
    valid = []
    expired = []
    for ref in runbook_references:
        if ref in valid_runbook_ids:
            valid.append(ref)
        else:
            expired.append(ref)
    return valid, expired


def validate_runbook_as_evidence(runbook: Runbook) -> tuple[bool, str]:
    """Check if a runbook can be used as high-confidence evidence.

    Returns (is_valid, reason).
    """
    if runbook.is_expired():
        return False, f"Runbook {runbook.runbook_id} has expired (effective_to: {runbook.effective_to})"

    if runbook.status.value != "valid":
        return False, f"Runbook {runbook.runbook_id} status is {runbook.status.value}, not valid"

    if runbook.needs_verification():
        return False, f"Runbook {runbook.runbook_id} needs re-verification (not verified recently)"

    return True, "Runbook is valid and can be used as evidence"


def determine_diagnosis_status(
    hypotheses: list[Hypothesis],
    traceability: TraceabilityReport,
) -> str:
    """Determine diagnosis status based on evidence quality.

    Rules:
    - DIAGNOSED: has evidence-backed hypothesis with HIGH/MEDIUM confidence
    - INCONCLUSIVE: evidence insufficient or all hypotheses are LOW confidence
    """
    if not hypotheses:
        return "INCONCLUSIVE"

    top = hypotheses[0]

    # No evidence at all
    if not top.supporting_evidence:
        return "INCONCLUSIVE"

    # Low confidence only
    if top.confidence == ConfidenceLevel.LOW:
        return "INCONCLUSIVE"

    # Evidence must be traceable
    if not traceability.is_fully_traceable:
        return "INCONCLUSIVE"

    return "DIAGNOSED"
