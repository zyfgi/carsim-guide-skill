"""Stable exception taxonomy for the CarSim core and discovery layers.

The compatibility base classes intentionally retain ``ValueError`` or
``RuntimeError`` semantics where existing callers already rely on them.
"""


class CarSimError(Exception):
    """Base class for errors raised by this skill."""


class CarSimEnvironmentError(RuntimeError, CarSimError):
    """The local runtime environment is incomplete or inconsistent."""


class CarSimNotFoundError(CarSimEnvironmentError):
    """A required CarSim installation component was not found."""


class LicenseError(CarSimEnvironmentError):
    """The solver could not acquire or load a CarSim license."""


class BaseResolutionError(ValueError, CarSimError):
    """A pinned Run Control execution context could not be resolved."""


class DatasetResolutionError(ValueError, CarSimError):
    """A dataset reference was missing, ambiguous, or unsafe."""


class ParameterResolutionError(ValueError, CarSimError):
    """A physical parameter could not be mapped to a verified keyword."""


class ScenarioValidationError(ValueError, CarSimError):
    """A scenario failed schema or semantic validation."""


class ScenarioCompileError(ValueError, CarSimError):
    """A validated scenario could not be compiled safely."""


class SolverExecutionError(RuntimeError, CarSimError):
    """The solver process could not be launched or returned a failure."""


class SolverTerminationError(SolverExecutionError):
    """The solver did not report normal simulation termination."""


class OutputMissingError(ValueError, CarSimError):
    """A required output artifact or channel is absent."""


class OutputParseError(ValueError, CarSimError):
    """A result file could not be parsed as finite numeric data."""


class OutputChannelError(ValueError, CarSimError):
    """An output channel is unknown or lacks verified unit metadata."""


class EchoValidationError(ValueError, CarSimError):
    """A requested override was absent or different in the solver echo."""


class CoSimulationError(RuntimeError, CarSimError):
    """A Simulink or external stepping integration failed."""


class VersionCompatibilityError(ValueError, CarSimError):
    """A version string or a version-specific route is invalid."""
