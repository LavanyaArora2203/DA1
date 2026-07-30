"""
load_hospital_general_info.py
------------------------------
Reads the raw Hospital General Information CSV (from fetch_data.py output),
splits it into:
  - dim_hospital            (one row per facility)
  - fact_measure_summary    (one row per facility x measure group, unpivoted)

and loads both into MySQL.

Usage:
    python load_hospital_general_info.py --csv ../raw/hospital_general_info_<timestamp>.csv
"""

import argparse
import pandas as pd
from sqlalchemy import create_engine

# --------------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------------
DB_URL = DATABASE_URL = "mysql+pymysql://root:Lavi%40220307@localhost/hospital_readmissions"


DIM_HOSPITAL_COLS = [
    "facility_id", "facility_name", "address", "citytown", "countyparish",
    "state", "zip_code", "telephone_number", "hospital_type",
    "hospital_ownership", "emergency_services", "hospital_overall_rating",
    "hospital_overall_rating_footnote",
    "meets_criteria_for_birthing_friendly_designation",
]

# Maps each measure group's prefix in the CSV to a clean group label
MEASURE_GROUPS = {
    "mort":    "mortality",
    "readm":   "readmission",
    "safety":  "safety",
    "pt_exp":  "patient_experience",
    "te":      "timely_effective",
}


def load_raw(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str)  # read as str first, cast deliberately below
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def build_dim_hospital(df: pd.DataFrame) -> pd.DataFrame:
    dim = df[DIM_HOSPITAL_COLS].copy()
    dim["emergency_services"] = dim["emergency_services"].str.lower().map(
        {"yes": True, "true": True, "no": False, "false": False}
    )
    dim["hospital_overall_rating"] = pd.to_numeric(
        dim["hospital_overall_rating"], errors="coerce"
    )
    dim = dim.drop_duplicates(subset="facility_id")
    return dim


def build_fact_measure_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for prefix, group_label in MEASURE_GROUPS.items():
        # Column names differ slightly per group; guard with .get-style access
        col_count       = f"count_of_facility_{prefix}_measures"
        col_group_count = f"{prefix}_group_measure_count"
        col_footnote    = f"{prefix}_group_footnote"
        col_better      = f"count_of_{prefix}_measures_better"
        col_no_diff     = f"count_of_{prefix}_measures_no_different"
        col_worse       = f"count_of_{prefix}_measures_worse"

        # Not every group has better/worse/no-different breakdowns (e.g. pt_exp, te
        # in this dataset don't) — fill with NA if the column doesn't exist rather
        # than crashing, since CMS's column set has changed across releases before.
        def col_or_na(col_name):
            return df[col_name] if col_name in df.columns else pd.NA

        chunk = pd.DataFrame({
            "facility_id":         df["facility_id"],
            "measure_group":       group_label,
            "facility_measure_count": pd.to_numeric(col_or_na(col_count), errors="coerce"),
            "group_measure_count":  pd.to_numeric(col_or_na(col_group_count), errors="coerce"),
            "count_better":         pd.to_numeric(col_or_na(col_better), errors="coerce"),
            "count_no_different":   pd.to_numeric(col_or_na(col_no_diff), errors="coerce"),
            "count_worse":          pd.to_numeric(col_or_na(col_worse), errors="coerce"),
            "group_footnote":       col_or_na(col_footnote),
        })
        rows.append(chunk)

    fact = pd.concat(rows, ignore_index=True)
    return fact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="Path to hospital_general_info CSV")
    parser.add_argument("--db-url", default=DB_URL, help="SQLAlchemy MySQL URL")
    args = parser.parse_args()

    df = load_raw(args.csv)
    dim_hospital = build_dim_hospital(df)
    fact_measure_summary = build_fact_measure_summary(df)

    print(f"dim_hospital: {len(dim_hospital)} rows")
    print(f"fact_measure_summary: {len(fact_measure_summary)} rows")

    engine = create_engine(args.db_url)

    # append (not replace) so we keep the PRIMARY KEY / FOREIGN KEY / column types
    # defined in schema.sql — pandas' auto-created "replace" tables lose all of that.
    with engine.begin() as conn:
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        conn.exec_driver_sql("TRUNCATE TABLE fact_measure_summary")
        conn.exec_driver_sql("TRUNCATE TABLE dim_hospital")
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")

    dim_hospital.to_sql("dim_hospital", engine, if_exists="append", index=False)
    fact_measure_summary.to_sql("fact_measure_summary", engine, if_exists="append", index=False)

    print("Loaded both tables into MySQL.")


if __name__ == "__main__":
    main()