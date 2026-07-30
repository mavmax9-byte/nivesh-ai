"""Committee-level, fail-closed exceptions (INVESTMENT_COMMITTEE_DESIGN.md
§9). Both are genuine, non-transient rejections -- like v0.9's
`InvestmentAdviceDetectedError`, retrying the identical inputs would not
produce a materially different outcome, so `ingestion/tasks.py` catches
both and does not retry."""

from fastapi import status

from nivesh.core.exceptions import NiveshError


class CommitteeQuorumNotMetError(NiveshError):
    """Raised when Fundamental Analyst -- the one mandatory specialist --
    did not succeed. Mirrors the zero-successes case: there is nothing
    trustworthy for the Chair to synthesize from."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "COMMITTEE_QUORUM_NOT_MET"


class ComplianceRejectedError(NiveshError):
    """Raised after Compliance rejects the Chair's draft. The rejection
    itself is still persisted as an auditable `compliance_review` row
    (§10) before this is raised -- the run fails closed, but the rejection
    does not vanish silently."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "COMPLIANCE_REJECTED"
