"""Roda o job de fumaça localmente e imprime o manifesto."""
import sys

from jobs.roofline_smoke import DEFAULT_INPUTS, roofline
from lab.manifest import run_job

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    m = run_job("roofline_smoke", roofline, DEFAULT_INPUTS, seed, runner="local")
    print(m.to_json())
