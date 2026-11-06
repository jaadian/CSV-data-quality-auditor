# Limitations

**Scope**
- Reports problems; never edits or cleans the data.
- Delimited text only (comma, semicolon, tab, pipe). No Excel, JSON, Parquet, XML.
- One process on one machine. About 10,000 rows per second (see [performance.md](performance.md)).

**Accuracy**
- Below `max_tracked_rows`, duplicates are counted with 128-bit hashes. A collision is possible in principle but not expected at these sizes. Above the limit a Bloom filter is used, which can overcount; the report then says `mode: approximate`.
- Median is exact up to 20,000 values per column, then estimated from a reservoir sample (`is_median_approximate: true`).
- Type inference looks at up to 5,000 values per column and is a suggestion. Your rules decide what is valid.
- Encoding detection can be wrong for single-byte legacy encodings. Pass `--encoding` when you know it.
- Cross-column rules compare numbers or ISO dates. Values that are neither are reported as violations, not compared as text.
- Each cell reports only its first failed rule, in the order listed in [validation_rules.md](validation_rules.md).

**The quality score**
- A heuristic defined by this project, not an industry measure.
- Completeness is counted over all cells, so one bad column in a wide file barely moves it: Titanic scores 97.24 while Cabin is 77% empty. Use the issue list, not the score, to decide what to fix.
- Validity is only included when rules are configured.

**Malformed input**
- Rows with the wrong number of fields stop the run by default. `--on-bad-rows skip` drops them and adds a high-severity issue.
- Blank headers are renamed `unnamed_<position>` with a medium issue. Duplicate headers stop the run.

**Privacy**
- `--mask-columns` hides values of those columns in samples, top values, duplicate examples and rule messages. Other columns and column names are still visible. Read a report before you share it.
- Reports store the input path as you typed it. Use a relative path if the absolute one is private.
