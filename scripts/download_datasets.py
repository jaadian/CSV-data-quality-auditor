"""Download the evaluation datasets listed in datasets/manifests/.

Usage:
    python scripts/download_datasets.py            # all datasets
    python scripts/download_datasets.py titanic    # one dataset

Files go to datasets/raw/ (git-ignored). Each download is checked against the
SHA-256 recorded in its manifest, so a changed upstream file is caught instead
of silently producing different results. Use --update-hash only when you have
looked at the new file and want to accept it.
"""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "datasets" / "manifests"
RAW = ROOT / "datasets" / "raw"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1 << 16):
            digest.update(block)
    return digest.hexdigest()


def download(manifest_path: Path, update_hash: bool) -> str:
    meta = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    name = meta["name"]
    if "source_url" not in meta:
        return f"{name}: skipped (generated locally, see scripts/generate_synthetic.py)"

    target = RAW / f"{name}.csv"
    if not target.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".part")
        with urllib.request.urlopen(meta["source_url"], timeout=60) as response:
            tmp.write_bytes(response.read())
        tmp.replace(target)

    actual = sha256_of(target)
    if actual == meta["sha256"]:
        return f"{name}: ok"
    if update_hash:
        text = manifest_path.read_text(encoding="utf-8").replace(meta["sha256"], actual)
        manifest_path.write_text(text, encoding="utf-8")
        return f"{name}: hash updated to {actual}"
    raise SystemExit(
        f"{name}: SHA-256 mismatch (expected {meta['sha256']}, got {actual}). "
        "The upstream file changed; inspect it, then rerun with --update-hash."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="dataset names (default: all)")
    parser.add_argument("--update-hash", action="store_true")
    args = parser.parse_args()

    manifests = sorted(MANIFESTS.glob("*.yaml"))
    if args.names:
        manifests = [m for m in manifests if m.stem in set(args.names)]
        if not manifests:
            sys.exit(f"No manifest found for: {', '.join(args.names)}")
    for manifest in manifests:
        print(download(manifest, args.update_hash))


if __name__ == "__main__":
    main()
