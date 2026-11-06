# Performance

Measured with `scripts/benchmark.py`, one run per row, each in a fresh process.

Machine: Linux x86_64, 2 cores, Intel Xeon @ 2.80 GHz, Python 3.13. No rules configured.

| Rows × columns | File size | Chunk size | Time (s) | Rows/s | Peak RSS (MiB) |
|---|---:|---:|---:|---:|---:|
| 100,000 × 20 | 18 MB | 10,000 | 10.74 | 9,314 | 146 |
| 100,000 × 20 | 18 MB | 50,000 | 10.49 | 9,530 | 227 |
| 1,000,000 × 20 | 183 MB | 50,000 | 87.0 | 11,494 | 293 |

Reproduce:

```bash
python scripts/generate_synthetic.py
python scripts/benchmark.py datasets/raw/synthetic_large.csv --chunk-sizes 10000 50000

python scripts/generate_synthetic.py --rows 1000000 \
    --out datasets/raw/synthetic_1m.csv --truth datasets/raw/synthetic_1m_truth.json
python scripts/benchmark.py datasets/raw/synthetic_1m.csv --chunk-sizes 50000
```

## Reading the numbers

- Peak memory depends on chunk size (each chunk is a pandas DataFrame of strings) and on the number of distinct rows (one 16-byte hash each, plus Python set overhead). Ten times more rows cost about 70 MiB more here, not ten times the memory.
- Above `max_tracked_rows` (500,000 by default) row hashes are moved into a Bloom filter. The 1M-row run crossed that limit, so its duplicate count is reported as `approximate`.
- Speed is limited by Python loops over cells in the missing-value checker and rule engine. Vectorising those with pandas string methods is the obvious next step.

An earlier version of this file reported 423 s for 100,000 rows on a Windows laptop. That benchmark ran inside `tracemalloc`, which adds large overhead, so those numbers are not comparable and were removed.
