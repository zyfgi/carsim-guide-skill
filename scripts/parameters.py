"""Generic scalar parameter override framework.

Two layers:
  - VehicleOverrides (scenario_schema): typed convenience API for the five
    verified sprung-mass parameters, SI in -> CarSim units out.
  - ScalarOverride (here): one verified keyword + native-unit value, for any
    parameter whose keyword and unit were confirmed in the actual dataset
    (via database_tools / run_echo) - never guessed.

Only field-verified keywords live in PARAMETER_REGISTRY; do not add
unverified ones for volume. Complex syntax (tables, PARSFILE, IMPORT/EXPORT,
INSTALL_* blocks) has no parser here: use carsim_batch unsafe_extra_lines.
"""
import math
import re
from dataclasses import dataclass
from typing import Optional

KEYWORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Keywords that configure the run itself; a scalar override may not touch them
# (they are owned by SimulationConfig / the scenario compiler).
PROTECTED_KEYWORDS = ("TSTART", "TSTOP", "TSTEP", "IPRINT", "OPT_STOP", "SSTOP",
                      "OPT_VS_FILETYPE", "OPT_ALL_WRITE", "OPT_ERROR_DIALOG")


@dataclass(frozen=True)
class ParameterSpec:
    keyword: str
    native_unit: str
    category: str
    dataset_family: Optional[str] = None
    description: Optional[str] = None


# Field-verified parameters only (mass verified exact; CG/inertia verified on
# a tested base - see SKILL.md for the Y_CG_SU static-split quirk). Values are
# supplied in the CarSim native unit listed here.
PARAMETER_REGISTRY = {
    "M_SU": ParameterSpec("M_SU", "kg", "sprung_mass", "Sprung_Mass",
                          "Sprung mass (absolute, not added payload)"),
    "LX_CG_SU": ParameterSpec("LX_CG_SU", "mm", "cg_position", "Sprung_Mass",
                              "Sprung-body CG x, vehicle frame"),
    "Y_CG_SU": ParameterSpec("Y_CG_SU", "mm", "cg_position", "Sprung_Mass",
                             "Sprung-body CG y (static split quirk: see SKILL.md)"),
    "H_CG_SU": ParameterSpec("H_CG_SU", "mm", "cg_position", "Sprung_Mass",
                             "Sprung-body CG height"),
    "IZZ_SU": ParameterSpec("IZZ_SU", "kg*m^2", "inertia", "Sprung_Mass",
                            "Sprung-body yaw inertia"),
}


@dataclass(frozen=True)
class ScalarOverride:
    keyword: str
    value: float

    def __post_init__(self):
        if not KEYWORD_RE.fullmatch(str(self.keyword)):
            raise ValueError("Invalid CarSim keyword: %r" % (self.keyword,))
        if not math.isfinite(self.value):
            raise ValueError("Override value must be finite: %s" % self.keyword)

    def lines(self):
        # %.12g matches the verified VehicleOverrides formatting: exact in
        # run_echo at the 1e-6 validation tolerance, human-readable in the .par
        return ["%s %.12g" % (self.keyword, self.value)]


def coerce_scalar_overrides(items):
    """Normalize None | ScalarOverride | (keyword, value) | {keyword: value}
    into a list of ScalarOverride."""
    if not items:
        return []
    out = []
    for item in items:
        if isinstance(item, ScalarOverride):
            out.append(item)
        elif isinstance(item, dict):
            if set(item) != {"keyword", "value"}:
                raise ValueError("Parameter mapping must be {keyword, value}")
            out.append(ScalarOverride(item["keyword"], item["value"]))
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            out.append(ScalarOverride(item[0], item[1]))
        else:
            raise ValueError("Cannot interpret parameter override: %r" % (item,))
    return out


def check_conflicts(overrides, protected=()):
    """Reject overrides aimed at run-configuration or typed-typed keywords."""
    protected_upper = {k.upper() for k in list(PROTECTED_KEYWORDS) + list(protected)}
    for override in overrides:
        if override.keyword.upper() in protected_upper:
            raise ValueError("Raw override conflicts with typed configuration: "
                             "%s %s" % (override.keyword, override.value))
