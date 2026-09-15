"""Print evidence-bearing output candidates without guessing a channel."""
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from output_registry import find_output_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--source", action="append", default=[])
    args = parser.parse_args()
    print(json.dumps([asdict(item) for item in
                      find_output_candidates(args.query, args.source)],
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
