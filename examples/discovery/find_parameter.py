"""Search a CarSim DATADIR and report parameter candidates."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from parameter_discovery import (
    discover_parameter,
    format_discovery_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--datadir", required=True)
    parser.add_argument("--root-dataset")
    parser.add_argument("--run-echo")
    args = parser.parse_args()
    report = discover_parameter(args.query, args.datadir,
                                args.root_dataset, args.run_echo)
    print(format_discovery_report(report))


if __name__ == "__main__":
    main()
