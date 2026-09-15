"""Verified scalar and deliberately limited structured CarSim overrides."""
import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import pairwise

from carsim_errors import DatasetResolutionError
from override_registry import OverrideCapability, override_capability

KEYWORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
ECHO_POLICIES = frozenset({"required", "best_effort", "none"})

# Runtime fields owned by the compiler/solver route, never generic overrides.
PROTECTED_RUNTIME_KEYWORDS = (
    "TSTART", "TSTOP", "TSTEP", "IPRINT", "OPT_STOP", "SSTOP",
    "OPT_VS_FILETYPE", "OPT_ALL_WRITE", "OPT_ERROR_DIALOG", "PROGDIR",
    "DATABASE_DIR", "DATADIR", "DLLFILE", "PRODUCT_ID", "PRODUCT_VER",
    "FILEBASE", "INPUT", "INPUTARCHIVE", "ECHO", "FINAL", "LOGFILE",
    "ERDFILE", "EXT_MODEL_STEP", "VEHICLE_CODE",
)
# Historical public name.
PROTECTED_KEYWORDS = PROTECTED_RUNTIME_KEYWORDS


def _validate_keyword(keyword: str) -> None:
    if not KEYWORD_RE.fullmatch(str(keyword)):
        raise ValueError(f"Invalid CarSim keyword: {keyword!r}")


def _validate_not_protected(keyword: str, protected: Iterable[str] = ()) -> None:
    blocked = {k.upper() for k in (*PROTECTED_RUNTIME_KEYWORDS, *tuple(protected))}
    if keyword.upper() in blocked:
        raise ValueError(f"Override conflicts with Core-managed runtime keyword: {keyword}")


@dataclass(frozen=True)
class ParameterSpec:
    """Verified parameter metadata."""

    keyword: str
    native_unit: str
    category: str
    dataset_family: str | None = None
    description: str | None = None


PARAMETER_REGISTRY = {
    "M_SU": ParameterSpec("M_SU", "kg", "sprung_mass", "Sprung_Mass",
                          "Sprung mass (absolute, not added payload)"),
    "LX_CG_SU": ParameterSpec("LX_CG_SU", "mm", "cg_position", "Sprung_Mass",
                              "Sprung-body CG x, vehicle frame"),
    "Y_CG_SU": ParameterSpec("Y_CG_SU", "mm", "cg_position", "Sprung_Mass",
                             "Sprung-body CG y; base-specific behavior must be verified"),
    "H_CG_SU": ParameterSpec("H_CG_SU", "mm", "cg_position", "Sprung_Mass",
                             "Sprung-body CG height"),
    "IZZ_SU": ParameterSpec("IZZ_SU", "kg*m^2", "inertia", "Sprung_Mass",
                            "Sprung-body yaw inertia"),
}


@dataclass(frozen=True)
class ScalarOverride:
    """One finite native-unit value and its post-run echo policy."""

    keyword: str
    value: float
    echo_validation: str | None = None

    def __post_init__(self) -> None:
        _validate_keyword(self.keyword)
        if self.echo_validation is None:
            policy = "required" if self.keyword.upper() in PARAMETER_REGISTRY else "best_effort"
            object.__setattr__(self, "echo_validation", policy)
        if not math.isfinite(self.value):
            raise ValueError(f"Override value must be finite: {self.keyword}")
        if self.echo_validation not in ECHO_POLICIES:
            raise ValueError(
                "echo_validation must be required, best_effort, or none")

    @property
    def capability(self) -> OverrideCapability:
        return override_capability("scalar", self.keyword)

    def lines(self) -> list[str]:
        """Serialize one plain CarSim keyword line."""
        return [f"{self.keyword} {self.value:.12g}"]


@dataclass(frozen=True)
class TableOverride:
    """Simple rectangular numeric table; not a general .par parser."""

    keyword: str
    rows: Sequence[Sequence[float]]
    columns: int | None = None
    independent_variable: str | None = None
    interpolation: str = "LINEAR_FLAT"

    def __post_init__(self) -> None:
        _validate_keyword(self.keyword)
        _validate_not_protected(self.keyword)
        if not self.rows:
            raise ValueError("TableOverride rows must not be empty")
        width = self.columns or len(self.rows[0])
        if width < 2 or any(len(row) != width for row in self.rows):
            raise ValueError("TableOverride rows must have one consistent shape")
        if not all(math.isfinite(float(value)) for row in self.rows for value in row):
            raise ValueError("TableOverride values must be finite")
        if self.independent_variable not in (None, "time"):
            raise ValueError("independent_variable must be None or 'time'")
        if self.independent_variable == "time":
            xs = [float(row[0]) for row in self.rows]
            if any(right <= left for left, right in pairwise(xs)):
                raise ValueError("Time-table first column must be strictly increasing")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.interpolation):
            raise ValueError("Invalid table interpolation")

    def lines(self) -> list[str]:
        """Serialize a basic ENDTABLE block."""
        body = [", ".join(f"{float(value):.17g}" for value in row)
                for row in self.rows]
        return [f"{self.keyword} {self.interpolation}", *body, "ENDTABLE"]

    @property
    def capability(self) -> OverrideCapability:
        return override_capability("table", self.keyword)


@dataclass(frozen=True)
class ReferenceOverride:
    """Dataset reference resolved by exact #FullDataName inside DATADIR."""

    keyword: str
    dataset_name: str

    def __post_init__(self) -> None:
        _validate_keyword(self.keyword)
        _validate_not_protected(self.keyword)
        if not self.dataset_name.strip():
            raise ValueError("dataset_name must not be empty")
        if any(sep in self.dataset_name for sep in ("/", "\\")):
            raise DatasetResolutionError(
                "ReferenceOverride accepts a dataset name, not an arbitrary path")

    def resolve(self, datadir: str) -> str:
        """Resolve one exact, in-DATADIR dataset identity."""
        from database_tools import find_datasets
        hits = [hit for hit in find_datasets(datadir, self.dataset_name)
                if hit["full_data_name"].casefold() == self.dataset_name.casefold()]
        if len(hits) != 1:
            state = "missing" if not hits else "ambiguous"
            raise DatasetResolutionError(
                f"Dataset reference {self.dataset_name!r} is {state}; found {len(hits)} exact matches")
        return hits[0]["path"]

    def lines(self, datadir: str) -> list[str]:
        """Serialize the reference after exact resolution."""
        return [f"{self.keyword} {self.resolve(datadir)}"]

    @property
    def capability(self) -> OverrideCapability:
        return override_capability("reference", self.keyword)

    @property
    def resolution_verification(self):
        """Exact in-DATADIR name resolution is deterministic."""
        from override_registry import VerificationLevel

        return VerificationLevel.VERIFIED

    @property
    def compatibility_verification(self):
        """Keyword-to-dataset-family compatibility still needs local proof."""
        from override_registry import VerificationLevel

        return VerificationLevel.CONTEXT_REQUIRED


@dataclass(frozen=True)
class RawOverride:
    """Explicit escape hatch with syntax-only, not semantic, validation."""

    raw_lines: Sequence[str]

    def __post_init__(self) -> None:
        if not self.raw_lines:
            raise ValueError("RawOverride lines must not be empty")
        for line in self.raw_lines:
            if "\n" in line or "\r" in line:
                raise ValueError("Supply one raw override line per list entry")
            token = line.split()[0] if line.split() else ""
            if token:
                _validate_not_protected(token)

    def lines(self) -> list[str]:
        """Return raw lines unchanged; no echo contract is implied."""
        return list(self.raw_lines)

    @property
    def capability(self) -> OverrideCapability:
        return override_capability("raw")


StructuredOverride = ScalarOverride | TableOverride | ReferenceOverride | RawOverride


def coerce_scalar_overrides(items: Iterable[object] | None) -> list[ScalarOverride]:
    """Normalize legacy scalar override input forms."""
    if not items:
        return []
    out: list[ScalarOverride] = []
    for item in items:
        if isinstance(item, ScalarOverride):
            out.append(item)
        elif isinstance(item, dict):
            allowed = {"keyword", "value", "echo_validation"}
            if not {"keyword", "value"}.issubset(item) or not set(item).issubset(allowed):
                raise ValueError("Parameter mapping must contain keyword/value and optional echo_validation")
            out.append(ScalarOverride(item["keyword"], item["value"],
                                      item.get("echo_validation")))
        elif isinstance(item, (tuple, list)) and len(item) in (2, 3):
            out.append(ScalarOverride(*item))
        else:
            raise ValueError(f"Cannot interpret parameter override: {item!r}")
    return out


def coerce_structured_overrides(items: Iterable[object] | None) -> list[StructuredOverride]:
    """Normalize typed override objects or scenario-schema mappings."""
    if not items:
        return []
    out: list[StructuredOverride] = []
    for item in items:
        if isinstance(item, (ScalarOverride, TableOverride, ReferenceOverride, RawOverride)):
            out.append(item)
            continue
        if not isinstance(item, dict):
            raise TypeError(f"Cannot interpret structured override: {item!r}")
        kind = item.get("type", "scalar")
        data = {key: value for key, value in item.items() if key != "type"}
        constructors = {"scalar": ScalarOverride, "table": TableOverride,
                        "reference": ReferenceOverride, "raw": RawOverride}
        try:
            out.append(constructors[kind](**data))
        except KeyError:
            raise ValueError(f"Unknown override type: {kind}") from None
    return out


def check_conflicts(overrides: Iterable[StructuredOverride], protected: Iterable[str] = ()) -> None:
    """Reject overrides aimed at runtime or another typed owner."""
    for override in overrides:
        keyword = getattr(override, "keyword", None)
        if keyword:
            _validate_not_protected(keyword, protected)
