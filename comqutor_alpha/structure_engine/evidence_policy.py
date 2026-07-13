"""Evidence admission rules applied before a Claim enters structure computing."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")


class EvidencePolicyError(ValueError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def normalize_evidence_text(value: str) -> str:
    return _SPACE.sub(" ", value).strip().casefold()


class EvidencePolicy:
    """Require specific report-grounded evidence, not claim repetition."""

    def validate(self, *, claim: str, evidence: str, report_text: str) -> None:
        normalized_claim = normalize_evidence_text(claim)
        normalized_evidence = normalize_evidence_text(evidence)
        normalized_report = normalize_evidence_text(report_text)
        if not normalized_evidence:
            raise EvidencePolicyError("empty_evidence", "evidence must not be empty")
        if normalized_claim == normalized_evidence:
            raise EvidencePolicyError(
                "evidence_repeats_claim", "evidence must not be an exact repetition of claim"
            )
        if normalized_evidence not in normalized_report:
            raise EvidencePolicyError(
                "ungrounded_evidence", "evidence must be a traceable span from the raw report"
            )
