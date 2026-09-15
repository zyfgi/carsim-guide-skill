"""Read-only CarSim database exploration.

Turns the grep recipes into a Python API an agent can call directly:
find datasets by #FullDataName, inspect dataset identity, follow PARSFILE
links, locate keywords, free-text search, and check what a run actually
echoed. Every function only reads; nothing here writes, replaces or renames.

Workflow for unknown parameters: natural language -> search_database_text /
find_datasets -> candidate keyword -> confirm unit & context in the dataset
and/or run_echo (inspect_echo_keyword) -> typed VehicleOverrides /
ScalarOverride or unsafe_extra_lines. Never guess a keyword.

These tools parse the documented plain-text surface of .par files only
(header comments, PARSFILE lines, keyword lines, tables). They are not a
complete CarSim dataset parser.
"""
import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from carsim_errors import DatasetResolutionError

HEADER_READ_LINES = 60
_KEYSPLIT = re.compile(r"^#(\w+)\s*(.*)$")


def _keymatch(line):
    match = _KEYSPLIT.match(line.strip())
    return (match.group(1), match.group(2).strip()) if match else None


def _par_files(datadir, roots=None):
    """Yield .par file paths under datadir, restricted to roots (subdirectory
    names or paths) when given."""
    datadir = Path(datadir).resolve()
    if roots:
        seen = set()
        for root in roots:
            root = datadir / root if not Path(root).is_absolute() else Path(root)
            root = root.resolve()
            try:
                root.relative_to(datadir)
            except ValueError:
                raise DatasetResolutionError(
                    "Database search roots must remain inside DATADIR: %s" % root) from None
            if root in seen or not root.exists():
                continue
            seen.add(root)
            for base, _, files in os.walk(root):
                for name in files:
                    if name.lower().endswith(".par"):
                        yield Path(base) / name
    else:
        for base, _, files in os.walk(datadir):
            for name in files:
                if name.lower().endswith(".par"):
                    yield Path(base) / name


def _library_of(datadir, path):
    try:
        return Path(path).resolve().relative_to(Path(datadir).resolve()).parts[0]
    except (ValueError, IndexError):
        return ""


def find_datasets(datadir, query, roots=None, limit=200):
    """Datasets whose #FullDataName contains <query> (case-insensitive).

    Returns [{"path", "full_data_name", "library"}]; newest/first ordering is
    filesystem order - selection is the caller's explicit decision.
    """
    needle = str(query).casefold()
    hits = []
    for path in _par_files(datadir, roots):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                head = [handle.readline() for _ in range(HEADER_READ_LINES)]
        except OSError:
            continue
        for line in head:
            if line.startswith("#FullDataName"):
                full = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
                if needle in full.casefold():
                    hits.append({"path": str(path), "full_data_name": full,
                                 "library": _library_of(datadir, path)})
                break
        if len(hits) >= limit:
            break
    return hits


def get_dataset_identity(path):
    """Header identity of a dataset file: #FileID/#DataSet/#Category/
    #FullDataName/#Modified ... (whatever the header carries). No UUID is
    required for use - #FullDataName is the human identity."""
    identity = {}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            for _ in range(HEADER_READ_LINES):
                line = handle.readline()
                if not line:
                    break
                if line.startswith("#"):
                    match = _keymatch(line)
                    if match:
                        identity[match[0]] = match[1]
                elif identity:
                    break
    except OSError as exc:
        raise ValueError("Cannot read dataset %s: %s" % (path, exc)) from exc
    return identity


def get_parsfile_links(path, datadir=None):
    """PARSFILE references of a dataset: [{"raw", "path", "exists"}].
    Relative references resolve against datadir when given, else the file's
    own directory."""
    links = []
    base = Path(datadir) if datadir else Path(path).parent
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line.startswith("PARSFILE"):
                raw = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
                if not raw:
                    continue
                candidate = Path(raw)
                if not candidate.is_absolute():
                    candidate = base / candidate
                links.append({"raw": raw, "path": str(candidate),
                              "exists": candidate.is_file()})
    return links


def resolve_dataset_tree(root, datadir=None, max_depth=3, allow_external=False):
    """Recursive PARSFILE expansion with cycle detection and a depth limit.
    Nodes: {"path", "identity", "links": [child nodes], "cycle": bool}."""
    data_root = Path(datadir).resolve() if datadir else None

    def walk(path, depth, stack, external=False):
        resolved = Path(path).resolve()
        node = {"path": str(resolved),
                "identity": get_dataset_identity(resolved),
                "links": [], "cycle": resolved in stack,
                "external": external}
        if node["cycle"] or depth >= max_depth:
            return node
        stack = stack | {resolved}
        for link in get_parsfile_links(resolved, datadir):
            child = Path(link["path"]).resolve()
            if child.is_file():
                child_external = bool(data_root and not _inside(child, data_root))
                if child_external and not allow_external:
                    identity = get_dataset_identity(child)
                    node["links"].append({
                        "path": str(child),
                        "identity": identity,
                        "links": [],
                        "cycle": child in stack,
                        "external": True,
                    })
                else:
                    node["links"].append(
                        walk(child, depth + 1, stack, child_external or external)
                    )
        return node

    if not Path(root).is_file():
        raise ValueError("Not a dataset file: %s" % root)
    return walk(root, 0, frozenset())


@dataclass(frozen=True)
class DatasetNode:
    """One dataset identity in a dependency graph."""

    path: str
    full_data_name: Optional[str]
    category: Optional[str]
    exists: bool = True
    external: bool = False


@dataclass(frozen=True)
class DatasetEdge:
    """One parsed reference between datasets."""

    source: str
    target: str
    keyword: str


@dataclass(frozen=True)
class GraphIssue:
    """Non-fatal graph condition requiring caller attention."""

    code: str
    path: str
    message: str


@dataclass
class DatasetGraph:
    """Explainable dependency graph and its structural warnings."""

    root: str
    nodes: Dict[str, DatasetNode] = field(default_factory=dict)
    edges: List[DatasetEdge] = field(default_factory=list)
    issues: List[GraphIssue] = field(default_factory=list)

    def issues_by_code(self, code: str) -> List[GraphIssue]:
        """Return graph issues with one stable code."""
        return [issue for issue in self.issues if issue.code == code]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def build_dependency_graph(root: str | Path, datadir: str | Path | None = None,
                           allow_external: bool = False,
                           max_depth: int = 10) -> DatasetGraph:
    """Build a PARSFILE dependency graph without modifying any dataset.

    Cycles, repeated references, missing targets, traversal depth limits and
    references outside DATADIR are retained as explicit issues.
    """
    root_path = Path(root).resolve()
    if not root_path.is_file():
        raise DatasetResolutionError("Not a dataset file: %s" % root)
    if max_depth < 0:
        raise ValueError("max_depth must be nonnegative")
    data_root = Path(datadir).resolve() if datadir else None
    graph = DatasetGraph(str(root_path))
    seen = set()

    def add_node(path: Path, exists: bool = True, external: bool = False) -> None:
        key = str(path.resolve())
        if key in graph.nodes:
            return
        identity = get_dataset_identity(path) if exists else {}
        graph.nodes[key] = DatasetNode(
            key,
            identity.get("FullDataName"),
            identity.get("Category"),
            exists,
            external,
        )

    def walk(path: Path, depth: int, stack: tuple[Path, ...]) -> None:
        resolved = path.resolve()
        node_external = bool(data_root and not _inside(resolved, data_root))
        add_node(resolved, external=node_external)
        seen.add(resolved)
        links = get_parsfile_links(resolved, data_root)
        if links and depth >= max_depth:
            graph.issues.append(GraphIssue(
                "depth_limit", str(resolved),
                "Dependencies were not traversed beyond max_depth=%s" % max_depth))
            return
        for link in links:
            target = Path(link["path"]).resolve()
            graph.edges.append(DatasetEdge(str(resolved), str(target), "PARSFILE"))
            external = bool(data_root and not _inside(target, data_root))
            if external:
                graph.issues.append(GraphIssue(
                    "external_reference", str(target),
                    "Reference resolves outside DATADIR"))
            if not target.is_file():
                add_node(target, False, external)
                graph.issues.append(GraphIssue(
                    "missing_reference", str(target),
                    "Referenced dataset does not exist"))
                continue
            if external and not allow_external:
                add_node(target, True, True)
                continue
            if target in stack or target == resolved:
                add_node(target, external=external)
                graph.issues.append(GraphIssue(
                    "cycle", str(target), "Dependency cycle detected"))
                continue
            if target in seen:
                graph.issues.append(GraphIssue(
                    "duplicate_dataset", str(target),
                    "Dataset is referenced by more than one traversal path"))
                continue
            walk(target, depth + 1, (*stack, resolved))

    walk(root_path, 0, ())
    return graph


def format_dependency_tree(graph: DatasetGraph) -> str:
    """Render a compact tree while preserving cycles/duplicates as markers."""
    children = {}
    for edge in graph.edges:
        children.setdefault(edge.source, []).append(edge.target)
    lines = []
    expanded = set()

    def label(path: str) -> str:
        node = graph.nodes[path]
        return node.full_data_name or Path(path).name

    def render(path: str, prefix: str = "", is_last: bool = True) -> None:
        marker = "└─ " if is_last else "├─ "
        lines.append((prefix + marker if prefix else "") + label(path))
        if path in expanded:
            lines[-1] += " [duplicate/cycle]"
            return
        expanded.add(path)
        kids = children.get(path, [])
        next_prefix = prefix + ("   " if is_last else "│  ") if prefix else ""
        for index, child in enumerate(kids):
            render(child, next_prefix, index == len(kids) - 1)

    render(graph.root)
    if graph.issues:
        lines.append("Warnings: " + ", ".join(sorted({i.code for i in graph.issues})))
    return "\n".join(lines)


def find_keyword(datadir, keyword, roots=None, limit=50):
    """Datasets containing <keyword> as a line-initial token (case-insensitive).
    Returns [{"path", "library", "full_data_name", "count", "first_line"}]."""
    pattern = re.compile(r"^\s*" + re.escape(str(keyword)) + r"\b", re.I)
    name_pattern = re.compile(r"^#FullDataName\s+(.+)$", re.I)
    hits = []
    for path in _par_files(datadir, roots):
        count, first_line, full_name = 0, None, ""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if pattern.match(line):
                        count += 1
                        if first_line is None:
                            first_line = line.strip()
                    elif name_pattern.match(line) and not full_name:
                        full_name = name_pattern.match(line).group(1).strip()
        except OSError:
            continue
        if count:
            hits.append({"path": str(path), "library": _library_of(datadir, path),
                         "full_data_name": full_name, "count": count,
                         "first_line": first_line})
            if len(hits) >= limit:
                break
    return hits


def search_database_text(datadir, text, roots=None, limit=100):
    """Case-insensitive free-text search across dataset files (grep analogue).
    Returns [{"path", "library", "line_number", "line"}]."""
    needle = str(text).casefold()
    hits = []
    for path in _par_files(datadir, roots):
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                for number, line in enumerate(handle, 1):
                    if needle in line.casefold():
                        hits.append({"path": str(path),
                                     "library": _library_of(datadir, path),
                                     "line_number": number,
                                     "line": line.strip()})
                        if len(hits) >= limit:
                            return hits
        except OSError:
            continue
    return hits


def inspect_echo_keyword(run_echo, keyword):
    """Lines of a run_echo.par that carry <keyword>: actual parsed values and
    the trailing comment. Returns [{"keyword", "values", "value", "comment",
    "line"}]. This is the post-run proof of what the solver actually used."""
    pattern = re.compile(r"^\s*" + re.escape(str(keyword)) + r"\b(.*)$", re.I)
    number = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")
    out = []
    with open(run_echo, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            match = pattern.match(line)
            if not match:
                continue
            rest = match.group(1)
            comment = ""
            if "!" in rest:
                rest, comment = rest.split("!", 1)
                comment = comment.strip()
            values = [float(v) for v in number.findall(rest)]
            out.append({"keyword": keyword, "values": values,
                        "value": values[-1] if values else None,
                        "comment": comment, "line": line.strip()})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",
                        choices=["find-dataset", "find-keyword", "search",
                                 "tree", "identity", "echo"])
    parser.add_argument("query", help="dataset text / keyword / dataset path")
    parser.add_argument("--datadir", help="database root (for find/search/tree)")
    parser.add_argument("--roots", nargs="*", help="restrict scan to these datadir subdirectories")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if args.command == "find-dataset":
        results = find_datasets(args.datadir, args.query, args.roots, args.limit)
    elif args.command == "find-keyword":
        results = find_keyword(args.datadir, args.query, args.roots, args.limit)
    elif args.command == "search":
        results = search_database_text(args.datadir, args.query, args.roots, args.limit)
    elif args.command == "tree":
        results = resolve_dataset_tree(args.query, args.datadir)
    elif args.command == "identity":
        results = get_dataset_identity(args.query)
    else:
        results = inspect_echo_keyword(args.query, args.datadir or "")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
