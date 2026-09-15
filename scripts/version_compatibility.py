"""Explicit, conservative CarSim version compatibility registry."""
import re
from dataclasses import dataclass

from carsim_errors import VersionCompatibilityError


@dataclass(frozen=True)
class CarSimVersion:
    """Parsed CarSim release identifier."""

    major: int
    minor: int
    raw: str

    @property
    def key(self) -> str:
        """Return normalized ``YYYY.minor`` spelling."""
        return f"{self.major}.{self.minor}"


@dataclass(frozen=True)
class CompatibilityStatus:
    """Compatibility evidence for one version."""

    version: CarSimVersion
    verified: bool
    features: frozenset[str]
    warning: str | None = None


# Only real solver evidence may be added here. 2024.0 is documented by the
# checked-in field verification records; parsing another version is not proof.
COMPATIBILITY: dict[str, frozenset[str]] = {
    "2024.0": frozenset({"cli_solver", "dll_64", "simfile_v1"}),
}


def parse_version(value: str) -> CarSimVersion:
    """Parse a version or install-path fragment without guessing a release."""
    match = re.search(r"(?:CarSim[ _-]?)?(\d{4})\.(\d+)", str(value), re.IGNORECASE)
    if not match:
        raise VersionCompatibilityError(
            "CarSim version must contain an explicit value such as 2024.0")
    return CarSimVersion(int(match.group(1)), int(match.group(2)), match.group(0))


def compatibility_status(value: str) -> CompatibilityStatus:
    """Return verified evidence or a non-blocking unverified warning."""
    version = parse_version(value)
    features = COMPATIBILITY.get(version.key, frozenset())
    if features:
        return CompatibilityStatus(version, True, features)
    return CompatibilityStatus(
        version, False, frozenset(),
        f"CarSim {version.key} is detected but unverified; attempting the "
        "generic compatible path and recording this status")


def supports(feature: str, value: str) -> bool:
    """Return true only when ``feature`` has evidence for ``value``."""
    return feature in compatibility_status(value).features
