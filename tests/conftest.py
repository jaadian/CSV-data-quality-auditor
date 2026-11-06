from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    f_dir = tmp_path / "fixtures"
    f_dir.mkdir(parents=True, exist_ok=True)
    return f_dir


@pytest.fixture
def clean_csv(fixtures_dir: Path) -> Path:
    csv_file = fixtures_dir / "clean.csv"
    csv_file.write_text(
        "id,name,age,email\n"
        "1,Alice,25,alice@example.com\n"
        "2,Bob,30,bob@example.com\n"
        "3,Charlie,35,charlie@example.com\n",
        encoding="utf-8",
    )
    return csv_file


@pytest.fixture
def dirty_csv(fixtures_dir: Path) -> Path:
    csv_file = fixtures_dir / "dirty.csv"
    csv_file.write_text(
        "customer_id,age,email,status\n"
        "00123,25,alice@example.com,active\n"
        "00124,NULL,bad_email,invalid_status\n"
        "00123,25,alice@example.com,active\n"
        "00125,-10,charlie@test.com,churned\n",
        encoding="utf-8",
    )
    return csv_file
