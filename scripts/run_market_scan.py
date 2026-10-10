"""Run/resume the Ethereum snapshot scan. --restart recomputes cached analyses."""
import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from blast_radius.config import load_config
from blast_radius.scan.runner import run_scan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("BLAST_RADIUS_HTTP_DELAY", str(load_config()["scan_config"]["live_miss_delay_seconds"]))
    out = run_scan(resume=not args.restart)
    print(f"Scanned ${out['total_scanned_usd']:,.0f} across {out['n_positions']}/{out['n_eligible']} positions; "
          f"mapped {out['coverage']['fully_looked_through_pct']:.1f}%; errors={len(out['errors'])}")
    if out["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
