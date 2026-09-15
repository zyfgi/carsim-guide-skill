"""Shared, fail-closed query normalization for discovery APIs."""

import re
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveryQuery:
    """Original wording plus literal search terms and verified aliases."""

    original: str
    search_terms: tuple[str, ...]
    aliases: tuple[str, ...] = ()


def normalized_terms(terms: Iterable[str] | None) -> tuple[str, ...]:
    """Normalize user-supplied physical terms without inventing identifiers."""
    if terms is None:
        return ()
    out: list[str] = []
    for term in terms:
        value = " ".join(str(term).strip().casefold().split())
        if value and value not in out:
            out.append(value)
    return tuple(out)


def ascii_query_terms(query: str) -> tuple[str, ...]:
    """Return an English/identifier phrase only when one is actually present."""
    text = " ".join(str(query).strip().casefold().split())
    if not text or not re.search(r"[a-z]", text):
        return ()
    return (text,)
