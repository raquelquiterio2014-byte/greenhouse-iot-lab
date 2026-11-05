"""Evaluate the Greenhouse IoT Lab pipeline without hardware or API keys."""
import argparse
import json
from pathlib import Path

from greenhouse.evaluation import SCENARIOS, evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS)
    parser.add_argument("--output", type=Path, default=Path("exports/v5_evaluation.json"))
    args = parser.parse_args()
    report = evaluate([args.scenario] if args.scenario else SCENARIOS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    for case in report["cases"]:
        print(f"{case['scenario']}: {'PASS' if case['passed'] else 'FAIL'} — {case['analysis']['status']}")
        for check, passed in case["checks"].items():
            if not passed:
                print(f"  Failed check: {check}")
    print(f"Report: {args.output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
