"""CLI for layered CarSim run diagnostics."""
import argparse

from diagnostics import diagnose_run, format_diagnostics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory")
    args = parser.parse_args()
    result = diagnose_run(args.run_directory)
    print(format_diagnostics(result))
    raise SystemExit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
