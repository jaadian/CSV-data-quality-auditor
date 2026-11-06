from hypothesis import given, settings
from hypothesis import strategies as st

from csv_auditor.config import AuditorConfig
from csv_auditor.core.auditor import CsvAuditor


@settings(max_examples=25, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.text(min_size=1, max_size=10, alphabet="abcdef0123456789"),
            st.sampled_from(["active", "churned", "NULL", "", "pending"]),
        ),
        min_size=1,
        max_size=30,
    )
)
def test_hypothesis_invariants(tmp_path_factory, rows):
    tmp_path = tmp_path_factory.mktemp("prop")
    csv_file = tmp_path / "prop.csv"

    csv_lines = ["col_a,col_b"]
    for a, b in rows:
        csv_lines.append(f"{a},{b}")
    csv_file.write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    auditor = CsvAuditor()
    result = auditor.audit(csv_file)

    assert 0.0 <= result.score.overall <= 100.0
    assert 0.0 <= result.score.completeness <= 100.0
    assert 0.0 <= result.score.uniqueness <= 100.0
    assert result.duplicates.exact_duplicate_rows >= 0
    assert result.metadata.total_rows == len(rows)

    for _col_name, stats in result.missing.items():
        assert 0 <= stats.missing_count <= len(rows)
        assert 0.0 <= stats.missing_percentage <= 100.0


@settings(max_examples=15, deadline=None)
@given(
    data=st.lists(
        st.tuples(st.integers(0, 100), st.text(min_size=1, max_size=5, alphabet="xyz")),
        min_size=5,
        max_size=25,
    )
)
def test_hypothesis_chunk_size_invariance(tmp_path_factory, data):
    tmp_path = tmp_path_factory.mktemp("chunk_inv")
    csv_file = tmp_path / "inv.csv"

    lines = ["num,txt"]
    for n, t in data:
        lines.append(f"{n},{t}")
    csv_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    res_chunk1 = CsvAuditor(config=AuditorConfig(chunk_size=1)).audit(csv_file)
    res_chunk5 = CsvAuditor(config=AuditorConfig(chunk_size=5)).audit(csv_file)
    res_chunk50 = CsvAuditor(config=AuditorConfig(chunk_size=50)).audit(csv_file)

    assert (
        res_chunk1.metadata.total_rows
        == res_chunk5.metadata.total_rows
        == res_chunk50.metadata.total_rows
    )
    assert (
        res_chunk1.duplicates.exact_duplicate_rows
        == res_chunk5.duplicates.exact_duplicate_rows
        == res_chunk50.duplicates.exact_duplicate_rows
    )
    assert (
        res_chunk1.missing["num"].missing_count
        == res_chunk5.missing["num"].missing_count
        == res_chunk50.missing["num"].missing_count
    )
    assert (
        res_chunk1.score.completeness
        == res_chunk5.score.completeness
        == res_chunk50.score.completeness
    )
