# Datasets

Nothing here is committed except the manifests. The files are downloaded or generated into `datasets/raw/`, which git ignores.

```bash
python scripts/download_datasets.py          # nine public CSVs, ~5 MB, SHA-256 checked
python scripts/generate_synthetic.py         # 100,000-row synthetic file + ground truth
python scripts/verify_datasets.py            # audit all ten and compare with the reference
```

Each `manifests/<name>.yaml` records the raw URL, the upstream repository, the SHA-256 of the file that was tested, and the rules file in `configs/datasets/`. If an upstream file changes, the download stops with a hash mismatch; inspect the new file and rerun with `--update-hash` to accept it.

Licenses of the upstream copies have not been verified. Check them before redistributing any of the data.

Results and notes: [docs/dataset_testing.md](../docs/dataset_testing.md).
