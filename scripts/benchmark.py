"""Measure audit time and peak memory on a CSV file.

Usage:
    python scripts/generate_synthetic.py --rows 1000000 --out datasets/raw/synthetic_1m.csv \
        --truth datasets/raw/synthetic_1m_truth.json
    python scripts/benchmark.py datasets/raw/synthetic_1m.csv --chunk-sizes 10000 50000

Each run happens in a fresh subprocess and reports its own peak RSS (Linux/macOS;
on macOS ru_maxrss is in bytes, so the MiB figure will be off by 1024x).
An earlier version ran under tracemalloc, which adds heavy overhead, so its
timings are not comparable. Peak RSS from getrusage is used instead.
"""

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

CHILD = """
import json, resource, sys, time
from csv_auditor.config import AuditorConfig
from csv_auditor.core.auditor import CsvAuditor
start = time.perf_counter()
result = CsvAuditor(AuditorConfig(chunk_size=int(sys.argv[2]))).audit(sys.argv[1])
seconds = time.perf_counter() - start
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # KiB on Linux
print(json.dumps({"rows": result.metadata.total_rows, "seconds": seconds, "peak_kib": peak}))
"""


def run_once(path: Path, chunk_size: int) -> dict:
    out = subprocess.run(
        [sys.executable, "-c", CHILD, str(path), str(chunk_size)],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(out.stdout)
    return {
        "chunk_size": chunk_size,
        "rows": data["rows"],
        "seconds": round(data["seconds"], 2),
        "rows_per_second": round(data["rows"] / data["seconds"]),
        "peak_rss_mib": round(data["peak_kib"] / 1024),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path)
    parser.add_argument("--chunk-sizes", type=int, nargs="+", default=[10_000, 50_000])
    args = parser.parse_args()
    if not args.csv.exists():
        sys.exit(f"{args.csv} not found. Run scripts/generate_synthetic.py first.")

    print(f"{platform.system()} {platform.machine()}, Python {platform.python_version()}")
    print("| Chunk size | Rows | Seconds | Rows/s | Peak RSS (MiB) |")
    print("|---:|---:|---:|---:|---:|")
    for size in args.chunk_sizes:
        r = run_once(args.csv, size)
        print(
            f"| {size:,} | {r['rows']:,} | {r['seconds']} | {r['rows_per_second']:,} | {r['peak_rss_mib']} |"
        )


if __name__ == "__main__":
    main()
