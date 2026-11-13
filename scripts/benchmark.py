"""Reproducible whole-process wall-time comparison, not a syscall microbenchmark."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def summarize(samples):
    ordered = sorted(samples)
    return {"runs": len(samples), "median_ms": statistics.median(samples),
            "p95_ms": ordered[math.ceil(len(samples) * 0.95) - 1],
            "min_ms": min(samples), "samples_ms": samples}


def measure(argv):
    environment = {key: value for key, value in os.environ.items() if key not in ("BASH_ENV", "ENV")}
    environment["MASH_HISTORY"] = ""
    started = time.perf_counter_ns()
    result = subprocess.run(argv, capture_output=True, timeout=10, env=environment)
    elapsed = (time.perf_counter_ns() - started) / 1_000_000
    if result.returncode:
        raise RuntimeError(f"benchmark command failed: {result.stderr.decode(errors='replace')}")
    return elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()
    if args.runs < 2 or args.warmups < 0:
        parser.error("use at least two runs and nonnegative warmups")
    bash = shutil.which("bash")
    if os.name != "posix" or not bash:
        parser.error("run on Linux with Bash and Python 3.10+")
    runners = {"mash": [sys.executable, str(ROOT / "mash.py"), "-c"],
               "bash": [bash, "--noprofile", "--norc", "-c"]}
    workloads = {"startup": "exit", "external_command": "/bin/true",
                 "pipeline": "printf 'one\\ntwo\\n' | wc -l"}
    report = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "python": sys.version,
              "bash": subprocess.check_output([bash, "--version"], text=True).splitlines()[0],
              "logical_cpus": os.cpu_count(), "warmups": args.warmups,
              "method": "whole-process wall time; warm cache; seeded interleaved order",
              "results": {}}
    rng = random.Random(0)
    for workload, command in workloads.items():
        samples = {name: [] for name in runners}
        for index in range(args.warmups + args.runs):
            order = list(runners)
            rng.shuffle(order)
            for name in order:
                elapsed = measure(runners[name] + [command])
                if index >= args.warmups:
                    samples[name].append(elapsed)
        report["results"][workload] = {name: summarize(values) for name, values in samples.items()}
        for name, values in report["results"][workload].items():
            print(f"{workload:18} {name:5} median {values['median_ms']:8.2f} ms  p95 {values['p95_ms']:8.2f} ms")
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved raw samples and environment: {args.output}")


if __name__ == "__main__":
    main()
