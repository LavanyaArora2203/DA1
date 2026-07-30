"""
load_hrrp_readmissions.py
--------------------------
Reads the raw HRRP (Hospital Readmissions Reduction Program) CSV from
fetch_data.py's output and loads it into fact_readmission_detail.

Usage:
    python load_hrrp_readmissions.py --csv ../raw/hrrp_readmissions_<timestamp>.csv
"""

import argparse
import pandas as pd
from sqlalchemy import create_engine

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
DB_URL = DATABASE_URL = "mysql+pymysql://root:Lavi%40220307@localhost/hospital_readmissions"

NUMERIC_COLS = [
    "excess_readmission_ratio",
    "predicted_readmission_rate",
    "expected_readmission_rate",
    "number_of_discharges",
    "number_of_readmissions",
]
DATE_COLS = ["start_date", "end_date"]


def load_and_clean(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]

    # CMS marks suppressed/not-available values as "Not Available" in HRRP —
    # coerce those and any other non-numeric junk to NaN rather than crashing.
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Drop rows with no facility_id or measure_name — can't key them
    before = len(df)
    df = df.dropna(subset=["facility_id", "measure_name"])
    dropped = before - len(df)
    if dropped:
        print(f"Dropped {dropped} rows missing facility_id or measure_name")

    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to hrrp_readmissions CSV")
    parser.add_argument("--db-url", default=DB_URL, help="SQLAlchemy MySQL URL")
    args = parser.parse_args()

    df = load_and_clean(args.csv)

    keep_cols = [
        "facility_id", "measure_name", "state", "excess_readmission_ratio",
        "predicted_readmission_rate", "expected_readmission_rate",
        "number_of_discharges", "number_of_readmissions",
        "start_date", "end_date", "footnote",
    ]
    df = df[[c for c in keep_cols if c in df.columns]]

    print(f"fact_readmission_detail: {len(df)} rows ready to load")
    print(f"Facilities with ratio > 1.0 (worse than expected): "
          f"{(df['excess_readmission_ratio'] > 1.0).sum()}")

    engine = create_engine(args.db_url)

    # append (not replace) so we keep the surrogate PRIMARY KEY, UNIQUE constraint,
    # and FOREIGN KEY defined in schema.sql.
    with engine.begin() as conn:
        conn.exec_driver_sql("TRUNCATE TABLE fact_readmission_detail")

    df.to_sql("fact_readmission_detail", engine, if_exists="append", index=False)

    print("Loaded fact_readmission_detail into MySQL.")


if __name__ == "__main__":
    main()