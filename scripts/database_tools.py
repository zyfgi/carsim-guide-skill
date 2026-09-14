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
from pathlib import Path

HEADER_READ_LINES = 60
_KEYSPLIT = re.compile(r"^#(\w+)\s*(.*)$")


def _keymatch(line):
    match = _KEYSPLIT.match(line.strip())
    return (match.group(1), match.group(2).strip()) if match else None


def _par_files(datadir, roots=None):
    """Yield .par file paths under datadir, restricted to roots (subdirectory
    names or paths) when given."""
    datadir = Path(datadir)
    if roots:
        seen = set()
        for root in roots:
            root = datadir / root if not Path(root).is_absolute() else Path(root)
            root = root.resolve()
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


def resolve_dataset_tree(root, datadir=None, max_depth=3):
    """Recursive PARSFILE expansion with cycle detection and a depth limit.
    Nodes: {"path", "identity", "links": [child nodes], "cycle": bool}."""
    def walk(path, depth, stack):
        resolved = Path(path).resolve()
        node = {"path": str(resolved),
                "identity": get_dataset_identity(resolved),
                "links": [], "cycle": resolved in stack}
        if node["cycle"] or depth >= max_depth:
            return node
        stack = stack | {resolved}
        for link in get_parsfile_links(resolved, datadir):
            child = Path(link["path"])
            if child.is_file():
                node["links"].append(walk(child, depth + 1, stack))
        return node

    if not Path(root).is_file():
        raise ValueError("Not a dataset file: %s" % root)
    return walk(root, 0, frozenset())


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
