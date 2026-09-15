"""Render the parsed dependency graph for one CarSim dataset."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from database_tools import build_dependency_graph, format_dependency_tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--datadir")
    parser.add_argument("--max-depth", type=int, default=10)
    args = parser.parse_args()
    graph = build_dependency_graph(args.dataset, args.datadir, args.max_depth)
    print(format_dependency_tree(graph))


if __name__ == "__main__":
    main()
