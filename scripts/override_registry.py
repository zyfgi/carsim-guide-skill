"""Evidence registry for structured override capabilities.

This registry describes what has actually been verified. It is deliberately
small: discovery words and plausible CarSim spellings never become entries.
"""

from dataclasses import dataclass
from enum import Enum


class VerificationLevel(str, Enum):
    """Strongest evidence currently available for an override path."""

    UNIT_TESTED = "unit_tested"
    CARSIM_TESTED = "carsim_tested"
    CONTEXT_REQUIRED = "context_required"


@dataclass(frozen=True)
class OverrideCapability:
    kind: str
    keyword: str | None
    dataset_family: str | None
    verification: VerificationLevel
    evidence: str


OVERRIDE_CAPABILITIES = (
    *(
        OverrideCapability(
            "scalar",
            keyword,
            "Sprung_Mass",
            VerificationLevel.CARSIM_TESTED,
            "P1 licensed CarSim run plus run_echo.par value verification",
        )
        for keyword in ("M_SU", "LX_CG_SU", "Y_CG_SU", "H_CG_SU", "IZZ_SU")
    ),
    OverrideCapability(
        "table",
        "SPEED_TARGET_TABLE",
        None,
        VerificationLevel.CARSIM_TESTED,
        "tests/functional_carsim.py structured table licensed regression",
    ),
    OverrideCapability(
        "scalar",
        None,
        None,
        VerificationLevel.CONTEXT_REQUIRED,
        "Generic keyword syntax is tested; meaning, unit, and echo availability require context",
    ),
    OverrideCapability(
        "table",
        None,
        None,
        VerificationLevel.CONTEXT_REQUIRED,
        "Generic table serialization is unit-tested; keyword/table schema requires context",
    ),
    OverrideCapability(
        "reference",
        None,
        None,
        VerificationLevel.CONTEXT_REQUIRED,
        "Dataset resolution is unit-tested; keyword-to-dataset compatibility is not licensed-tested",
    ),
    OverrideCapability(
        "raw",
        None,
        None,
        VerificationLevel.CONTEXT_REQUIRED,
        "Syntax guard only; semantic validation remains the caller's responsibility",
    ),
)


def override_capability(
    kind: str, keyword: str | None = None, dataset_family: str | None = None
) -> OverrideCapability:
    """Return the most specific checked-in capability, falling back by kind."""
    normalized_kind = str(kind).casefold()
    normalized_keyword = keyword.upper() if keyword else None
    for capability in OVERRIDE_CAPABILITIES:
        if (
            capability.kind == normalized_kind
            and capability.keyword == normalized_keyword
            and (
                capability.dataset_family is None
                or dataset_family is None
                or capability.dataset_family == dataset_family
            )
        ):
            return capability
    for capability in OVERRIDE_CAPABILITIES:
        if capability.kind == normalized_kind and capability.keyword is None:
            return capability
    raise ValueError(f"Unknown override kind: {kind}")
