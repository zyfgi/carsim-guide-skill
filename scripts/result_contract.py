"""Backward-compatible facade for the P2 output registry."""
from output_registry import (
    OUTPUT_REGISTRY as CHANNEL_REGISTRY,
    OutputSpec as Channel,
    UNRELIABLE_COLS,
    WRT_ALIASES,
    output_spec,
)

# P1 public name retained. Natural-language aliases live in output_registry.
OUTPUT_ALIASES = WRT_ALIASES


def channel(name: str) -> Channel:
    """Return the verified channel specification."""
    return output_spec(name)
