import hashlib
import math

import pandas as pd

from csv_auditor.models import DuplicateReport, Issue, Severity


class SimpleBloomFilter:
    def __init__(self, capacity: int = 1_000_000, error_rate: float = 0.01) -> None:
        self.capacity = capacity
        self.error_rate = error_rate
        self.num_bits = int(-1 * (capacity * math.log(error_rate)) / (math.log(2) ** 2))
        self.num_hashes = int((self.num_bits / capacity) * math.log(2))
        self.byte_array = bytearray((self.num_bits + 7) // 8)

    def _get_hashes(self, data: bytes) -> list[int]:
        h1 = int.from_bytes(
            hashlib.blake2b(data, digest_size=8, salt=b"bloom_h1").digest(), "little"
        )
        h2 = int.from_bytes(
            hashlib.blake2b(data, digest_size=8, salt=b"bloom_h2").digest(), "little"
        )
        return [(h1 + i * h2) % self.num_bits for i in range(self.num_hashes)]

    def add_and_check(self, data: bytes) -> bool:
        indices = self._get_hashes(data)
        seen = True
        for bit_idx in indices:
            byte_pos = bit_idx // 8
            bit_mask = 1 << (bit_idx % 8)
            if not (self.byte_array[byte_pos] & bit_mask):
                seen = False
                self.byte_array[byte_pos] |= bit_mask
        return seen


class DuplicateChecker:
    def __init__(
        self,
        key_columns: list[list[str]] | None = None,
        max_tracked_rows: int = 500_000,
        max_examples: int = 5,
        check_normalized: bool = False,
        mask_columns: set[str] | None = None,
    ) -> None:
        self.key_columns = key_columns or []
        self.max_tracked_rows = max_tracked_rows
        self.max_examples = max_examples
        self.check_normalized = check_normalized
        self.mask_columns = mask_columns or set()

        self.exact_hashes: set[bytes] = set()
        self.bloom_filter: SimpleBloomFilter | None = None
        self.exact_duplicates_count = 0
        self.total_rows = 0

        self.key_seen: dict[str, set[bytes]] = {self._key_repr(k): set() for k in self.key_columns}
        self.key_bloom: dict[str, SimpleBloomFilter] = {}
        self.key_duplicates_count: dict[str, int] = {self._key_repr(k): 0 for k in self.key_columns}
        self.sample_duplicate_keys: dict[str, list[str]] = {
            self._key_repr(k): [] for k in self.key_columns
        }

        self.potential_normalized_duplicates = 0
        self.normalized_hashes: set[bytes] = set()

    def _key_repr(self, keys: list[str]) -> str:
        return "+".join(keys)

    def _hash_row(self, values: list[str]) -> bytes:
        # Length-prefix encoding prevents collisions between distinct field boundaries.
        digest = hashlib.blake2b(digest_size=16)
        for value in values:
            raw = value.encode("utf-8")
            digest.update(len(raw).to_bytes(8, "big"))
            digest.update(raw)
        return digest.digest()

    def _hash_normalized(self, values: list[str]) -> bytes:
        return self._hash_row([val.strip().lower() for val in values])

    def update(self, chunk: pd.DataFrame) -> None:
        cols = chunk.columns.tolist()
        num_rows = len(chunk)
        self.total_rows += num_rows

        for row in chunk.itertuples(index=False, name=None):
            row_vals = [str(x) for x in row]
            h = self._hash_row(row_vals)

            if self.bloom_filter is not None:
                if self.bloom_filter.add_and_check(h):
                    self.exact_duplicates_count += 1
            else:
                if h in self.exact_hashes:
                    self.exact_duplicates_count += 1
                else:
                    self.exact_hashes.add(h)
                    if len(self.exact_hashes) > self.max_tracked_rows:
                        self.bloom_filter = SimpleBloomFilter(capacity=self.max_tracked_rows * 2)
                        for existing_hash in self.exact_hashes:
                            self.bloom_filter.add_and_check(existing_hash)
                        self.exact_hashes.clear()

            if self.check_normalized:
                nh = self._hash_normalized(row_vals)
                if nh in self.normalized_hashes:
                    self.potential_normalized_duplicates += 1
                else:
                    self.normalized_hashes.add(nh)

        for key_cols in self.key_columns:
            key_name = self._key_repr(key_cols)
            if not all(k in cols for k in key_cols):
                continue

            for values in chunk[key_cols].itertuples(index=False, name=None):
                raw_values = [str(v) for v in values]
                key_hash = self._hash_row(raw_values)
                if key_name in self.key_bloom:
                    already_seen = self.key_bloom[key_name].add_and_check(key_hash)
                else:
                    already_seen = key_hash in self.key_seen[key_name]
                    if not already_seen:
                        self.key_seen[key_name].add(key_hash)
                        if len(self.key_seen[key_name]) > self.max_tracked_rows:
                            bloom = SimpleBloomFilter(capacity=max(1, self.max_tracked_rows * 2))
                            for old_hash in self.key_seen[key_name]:
                                bloom.add_and_check(old_hash)
                            self.key_bloom[key_name] = bloom
                            self.key_seen[key_name].clear()
                if already_seen:
                    self.key_duplicates_count[key_name] += 1
                    if len(self.sample_duplicate_keys[key_name]) < self.max_examples:
                        safe_values = [
                            "***" if col in self.mask_columns else value
                            for col, value in zip(key_cols, raw_values, strict=True)
                        ]
                        safe_key = " | ".join(safe_values)
                        if safe_key not in self.sample_duplicate_keys[key_name]:
                            self.sample_duplicate_keys[key_name].append(safe_key)

    def finalize(self) -> tuple[DuplicateReport, list[Issue]]:
        mode = "approximate" if self.bloom_filter is not None or self.key_bloom else "exact"
        unique_rows = self.total_rows - self.exact_duplicates_count

        report = DuplicateReport(
            exact_duplicate_rows=self.exact_duplicates_count,
            unique_rows=unique_rows,
            total_rows=self.total_rows,
            mode=mode,
            key_duplicates=self.key_duplicates_count,
            sample_duplicate_keys=self.sample_duplicate_keys,
        )

        issues: list[Issue] = []
        if self.exact_duplicates_count > 0:
            issues.append(
                Issue(
                    rule_name="exact_duplicate_rows",
                    message=f"Found {self.exact_duplicates_count} duplicate row(s) out of {self.total_rows} total rows (row mode: {'approximate' if self.bloom_filter else 'exact'})",
                    severity=Severity.HIGH,
                )
            )

        for key_name, count in self.key_duplicates_count.items():
            if count > 0:
                samples = self.sample_duplicate_keys[key_name]
                sample_str = ", ".join(f"'{s}'" for s in samples[:3])
                issues.append(
                    Issue(
                        rule_name="key_uniqueness_violation",
                        column=key_name,
                        message=f"Key '{key_name}' violated uniqueness with {count} duplicate occurrence(s) ({'approximate' if key_name in self.key_bloom else 'exact'}). Examples: {sample_str}",
                        severity=Severity.HIGH,
                    )
                )

        if (
            self.check_normalized
            and self.potential_normalized_duplicates > self.exact_duplicates_count
        ):
            potential_excess = self.potential_normalized_duplicates - self.exact_duplicates_count
            issues.append(
                Issue(
                    rule_name="potential_normalized_duplicates",
                    message=f"Detected {potential_excess} potential duplicates with case/whitespace variations",
                    severity=Severity.LOW,
                )
            )

        return report, issues
