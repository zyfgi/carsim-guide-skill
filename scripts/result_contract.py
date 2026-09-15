"""Stable facade for verified output metadata and SI conversions."""
from output_registry import (
    OUTPUT_REGISTRY as CHANNEL_REGISTRY,
    OutputSpec as Channel,
    UNRELIABLE_COLS,
    WRT_ALIASES,
    output_spec,
)

__all__ = ["CHANNEL_REGISTRY", "Channel", "OUTPUT_ALIASES", "UNRELIABLE_COLS", "channel"]

# Public constants remain stable; natural-language aliases live in output_registry.
OUTPUT_ALIASES = WRT_ALIASES


def channel(name: str) -> Channel:
    """Return the verified channel specification."""
    return output_spec(name)
