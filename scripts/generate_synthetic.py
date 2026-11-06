import argparse
import json
import random
from pathlib import Path


def generate_synthetic_data(
    output_path: Path,
    ground_truth_path: Path,
    num_rows: int = 100_000,
    seed: int = 42,
) -> None:
    rng = random.Random(seed)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ground_truth_path.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "tx_id",
        "account_id",
        "customer_name",
        "amount",
        "fee",
        "currency",
        "tx_type",
        "status",
        "created_at",
        "settled_at",
        "is_flagged",
        "risk_score",
        "country_code",
        "device_type",
        "ip_address",
        "card_type",
        "merchant_id",
        "terminal_id",
        "notes",
        "batch_id",
    ]

    total_duplicates = 0
    total_missing_cells = 0
    negative_amounts = 0
    invalid_dates = 0

    chunk1_duplicate_record = None

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(headers) + "\n")

        for idx in range(1, num_rows + 1):
            if idx == 10:
                chunk1_duplicate_record = (
                    "TX-00000010,0004921,John Doe,125.50,1.50,USD,TRANSFER,COMPLETED,"
                    "2026-01-10 10:00:00,2026-01-10 10:05:00,False,15,US,mobile,192.168.1.1,"
                    "VISA,M-1001,T-501,Initial transfer,B-1\n"
                )
                f.write(chunk1_duplicate_record)
                continue

            if idx == 50_015 and chunk1_duplicate_record is not None:
                f.write(chunk1_duplicate_record)
                total_duplicates += 1
                continue

            tx_id = f"TX-{idx:08d}"
            account_id = f"000{rng.randint(1000, 9999)}"
            customer_name = f"User_{idx % 5000}"

            if rng.random() < 0.02:
                amount = -1 * round(rng.uniform(10.0, 500.0), 2)
                negative_amounts += 1
            else:
                amount = round(rng.uniform(1.0, 5000.0), 2)

            fee = round(amount * 0.015, 2)
            currency = rng.choice(["USD", "EUR", "GBP", "CAD"])
            tx_type = rng.choice(["PAYMENT", "TRANSFER", "REFUND", "WITHDRAWAL"])
            status = rng.choice(["COMPLETED", "PENDING", "FAILED"])

            if rng.random() < 0.01:
                created_at = "2026-99-99 00:00:00"
                invalid_dates += 1
            else:
                created_at = f"2026-{rng.randint(1, 11):02d}-{rng.randint(1, 28):02d} 12:00:00"

            settled_at = created_at
            is_flagged = "True" if rng.random() < 0.05 else "False"
            risk_score = rng.randint(0, 100)
            country = rng.choice(["US", "GB", "DE", "FR", "CA"])
            device = rng.choice(["mobile", "desktop", "tablet"])
            ip_addr = f"10.0.{rng.randint(1, 254)}.{rng.randint(1, 254)}"
            card = rng.choice(["VISA", "MASTERCARD", "AMEX"])
            merchant = f"M-{rng.randint(1000, 9999)}"
            terminal = f"T-{rng.randint(100, 999)}"

            if rng.random() < 0.05:
                notes = rng.choice(["NULL", "N/A", "", "-"])
                total_missing_cells += 1
            else:
                notes = f"Transaction note {idx}"

            batch_id = f"B-{idx // 1000}"

            row = [
                tx_id,
                account_id,
                customer_name,
                str(amount),
                str(fee),
                currency,
                tx_type,
                status,
                created_at,
                settled_at,
                is_flagged,
                str(risk_score),
                country,
                device,
                ip_addr,
                card,
                merchant,
                terminal,
                notes,
                batch_id,
            ]
            f.write(",".join(row) + "\n")

    ground_truth = {
        "num_rows": num_rows,
        "num_columns": len(headers),
        "injected_cross_chunk_duplicates": total_duplicates,
        "injected_negative_amounts": negative_amounts,
        "injected_invalid_dates": invalid_dates,
        "injected_missing_notes": total_missing_cells,
        "seed": seed,
    }

    ground_truth_path.write_text(json.dumps(ground_truth, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate synthetic large dataset with known ground truth"
    )
    parser.add_argument("--rows", type=int, default=100_000, help="Number of rows to generate")
    parser.add_argument("--out", type=Path, default=Path("datasets/raw/synthetic_large.csv"))
    parser.add_argument(
        "--truth", type=Path, default=Path("datasets/raw/synthetic_large_truth.json")
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    generate_synthetic_data(args.out, args.truth, args.rows, args.seed)
