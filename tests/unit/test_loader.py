from pathlib import Path

from csv_auditor.ingestion.loader import iter_chunks
from csv_auditor.ingestion.sniffer import sniff_csv


def test_loader_preserves_leading_zeros(tmp_path: Path):
    csv_file = tmp_path / "leading_zeros.csv"
    csv_file.write_text("code,amount\n00123,45.50\n000456,100\n", encoding="utf-8")
    sniff = sniff_csv(csv_file)
    chunks = list(iter_chunks(csv_file, sniff, chunk_size=10))
    assert len(chunks) == 1
    df = chunks[0]
    assert df["code"].iloc[0] == "00123"
    assert df["code"].iloc[1] == "000456"
    assert df["amount"].iloc[0] == "45.50"


def test_loader_chunking_boundaries(tmp_path: Path):
    csv_file = tmp_path / "chunked.csv"
    lines = ["id,val"] + [f"{i},val_{i}" for i in range(10)]
    csv_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    sniff = sniff_csv(csv_file)
    chunks = list(iter_chunks(csv_file, sniff, chunk_size=3))
    assert len(chunks) == 4
    total_loaded = sum(len(c) for c in chunks)
    assert total_loaded == 10
