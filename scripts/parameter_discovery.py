"""Deterministic physical-term to CarSim parameter candidate discovery."""
import re
from dataclasses import dataclass, field
from pathlib import Path

import database_tools as database
from discovery_query import DiscoveryQuery, ascii_query_terms, normalized_terms
from parameters import KEYWORD_RE, PARAMETER_REGISTRY

CONFIDENCE_LEVELS = frozenset({"verified", "strong", "weak"})

# Every alias maps only to a registry entry with checked-in verification notes.
PARAMETER_ALIASES = {
    "sprung mass": ("M_SU", "P1 field verification / run echo"),
    "sprung-body yaw inertia": ("IZZ_SU", "P1 field verification / run echo"),
    "yaw inertia": ("IZZ_SU", "P1 field verification / run echo"),
    "sprung-body cg height": ("H_CG_SU", "P1 field verification / run echo"),
}

PARAMETER_PHYSICAL_TERMS = {
    "前悬架弹簧刚度": ("front suspension spring stiffness", "front spring stiffness"),
    "转向系统刚度": ("steering stiffness", "steering system stiffness"),
}


@dataclass(frozen=True)
class ParameterCandidate:
    """One evidence-bearing parameter candidate."""

    keyword: str
    dataset_path: str
    dataset_name: str | None
    nearby_text: str | None
    unit_hint: str | None
    category: str | None
    confidence: str
    reason: str

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError("confidence must be verified, strong, or weak")


@dataclass
class ParameterDiscoveryReport:
    """Ordered candidates; only registry/alias proof sets ``resolved``."""

    query: str
    candidates: list[ParameterCandidate] = field(default_factory=list)
    unresolved: bool = False
    search_terms: tuple[str, ...] = ()

    @property
    def resolved(self) -> ParameterCandidate | None:
        verified = [c for c in self.candidates if c.confidence == "verified"]
        return verified[0] if len(verified) == 1 else None

    @property
    def ambiguous(self) -> bool:
        viable = [c for c in self.candidates if c.confidence in {"verified", "strong"}]
        return len(viable) > 1


def _registry_candidate(keyword: str, reason: str) -> ParameterCandidate:
    spec = PARAMETER_REGISTRY[keyword]
    return ParameterCandidate(
        keyword, "", spec.dataset_family, spec.description, spec.native_unit,
        spec.category, "verified", reason)


def _identity(path: str) -> tuple[str | None, str | None]:
    identity = database.get_dataset_identity(path)
    return identity.get("FullDataName"), identity.get("Category")


def normalize_parameter_query(
    query: str, search_terms: list[str] | tuple[str, ...] | None = None
) -> DiscoveryQuery:
    """Normalize physical terms while preserving the no-guessed-keyword rule."""
    original = " ".join(str(query).strip().split())
    alias = PARAMETER_ALIASES.get(original.casefold())
    aliases = (alias[0],) if alias else ()
    if search_terms is not None:
        terms = normalized_terms(search_terms)
    else:
        terms = normalized_terms(PARAMETER_PHYSICAL_TERMS.get(original, ()))
        if not terms:
            terms = ascii_query_terms(original)
    return DiscoveryQuery(original, terms, aliases)


def discover_parameter(query: str, datadir: str | Path | None = None,
                       root_dataset: str | Path | None = None,
                       run_echo: str | Path | None = None,
                       limit: int = 50, *,
                       search_terms: list[str] | tuple[str, ...] | None = None
                       ) -> ParameterDiscoveryReport:
    """Apply the P2 discovery order and return candidates without guessing.

    A unique database hit remains ``strong`` until its unit/meaning is checked
    against the actual dataset and run echo; it is not silently promoted.
    """
    normalized = normalize_parameter_query(query, search_terms)
    text = normalized.original
    upper = text.upper()
    if upper in PARAMETER_REGISTRY:
        return ParameterDiscoveryReport(
            text, [_registry_candidate(upper, "exact PARAMETER_REGISTRY match")],
            search_terms=normalized.search_terms)
    if normalized.aliases:
        return ParameterDiscoveryReport(
            text,
            [_registry_candidate(normalized.aliases[0], "verified alias")],
            search_terms=normalized.search_terms,
        )
    if not datadir or not normalized.search_terms:
        return ParameterDiscoveryReport(
            text, [], True, search_terms=normalized.search_terms)

    allowed_paths = None
    if root_dataset:
        graph = database.build_dependency_graph(root_dataset, datadir)
        allowed_paths = {str(Path(path).resolve()) for path in graph.nodes}

    candidates = {}

    # 3. Exact keyword search.
    for term in normalized.search_terms:
        if not KEYWORD_RE.fullmatch(term):
            continue
        for hit in database.find_keyword(datadir, term, limit=limit):
            if allowed_paths is not None and str(Path(hit["path"]).resolve()) not in allowed_paths:
                continue
            name, category = _identity(hit["path"])
            keyword = term.upper()
            candidates[(keyword, hit["path"])] = ParameterCandidate(
                keyword, hit["path"], name, hit["first_line"], None, category,
                "strong", "exact line-initial keyword match")

    # 4. Dataset text search. Extract only a literal line-initial token.
    dataset_hits = []
    text_hits = []
    for term in normalized.search_terms:
        dataset_hits.extend(database.find_datasets(datadir, term, limit=limit))
        text_hits.extend(database.search_database_text(datadir, term, limit=limit))
    for hit in dataset_hits[:limit]:
        if allowed_paths is not None and str(Path(hit["path"]).resolve()) not in allowed_paths:
            continue
        try:
            lines = Path(hit["path"]).read_text(
                encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\b", line)
            if not match or line.lstrip().startswith("#"):
                continue
            keyword = match.group(1).upper()
            if keyword in {"PARSFILE", "END", "ENDTABLE"}:
                continue
            candidates.setdefault((keyword, hit["path"]), ParameterCandidate(
                keyword, hit["path"], hit["full_data_name"], line.strip(), None,
                hit.get("library"), "weak",
                "keyword in a dataset whose verified name matches the query"))
    for hit in text_hits[:limit]:
        if allowed_paths is not None and str(Path(hit["path"]).resolve()) not in allowed_paths:
            continue
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\b", hit["line"])
        if not match or hit["line"].lstrip().startswith("#"):
            continue
        keyword = match.group(1).upper()
        if keyword in {"PARSFILE", "END", "ENDTABLE"}:
            continue
        name, category = _identity(hit["path"])
        candidates.setdefault((keyword, hit["path"]), ParameterCandidate(
            keyword, hit["path"], name, hit["line"], None, category,
            "weak", "free-text dataset match; verify meaning and unit"))

    # 5 is represented by allowed_paths; 6 adds echo evidence for literal keywords.
    if run_echo:
        for term in normalized.search_terms:
            if not KEYWORD_RE.fullmatch(term):
                continue
            keyword = term.upper()
            for row in database.inspect_echo_keyword(run_echo, term):
                candidates[(keyword, str(run_echo))] = ParameterCandidate(
                    keyword, str(run_echo), "run echo", row["line"],
                    row["comment"] or None, None, "strong",
                    "keyword present in run echo; unit still requires confirmation")

    result = list(candidates.values())
    rank = {"verified": 0, "strong": 1, "weak": 2}
    result.sort(key=lambda item: (rank[item.confidence], item.keyword, item.dataset_path))
    return ParameterDiscoveryReport(
        text, result, not result, search_terms=normalized.search_terms)


def format_discovery_report(report: ParameterDiscoveryReport) -> str:
    """Format candidates for an agent/user decision."""
    if report.unresolved:
        return f"Unresolved parameter: {report.query}. No keyword was guessed."
    blocks = []
    for index, item in enumerate(report.candidates, 1):
        blocks.append(
            f"Candidate {index}\nkeyword: {item.keyword}\ndataset: "
            f"{item.dataset_name or item.dataset_path or 'verified registry'}\n"
            f"context: {item.nearby_text or '-'}\nunit: {item.unit_hint or 'unverified'}\n"
            f"confidence: {item.confidence}\nreason: {item.reason}")
    return "\n\n".join(blocks)
